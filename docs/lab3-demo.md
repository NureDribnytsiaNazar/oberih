# Демонстрація ЛБ3: бізнес-логіка та адміністрування

Покрокова інструкція для показу (і запису відео) з командами PowerShell. Усі
команди виконуються в одному вікні PowerShell; сервер працює в іншому.

## 0. Підготовка

Найпростіше почати з чистої бази (команда `down -v` **видаляє всі дані**
локальної БД):

```powershell
cd D:\ARK\oberih
docker compose down -v
docker compose up -d db

cd server
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m scripts.init_ca
$env:SEED_PASSWORD = "Demo-Password-1"
python -m scripts.seed
```

В окремому вікні запустіть сервер (фоновий виконавець таймерів стартує
разом із ним):

```powershell
cd D:\ARK\oberih\server
.venv\Scripts\Activate.ps1
uvicorn app.main:app
```

Допоміжна функція для запитів. Вона показує тіло відповіді й у разі помилки,
тому коди помилок видно одразу:

```powershell
$B = "http://localhost:8000/api/v1"
$Pwd = "Demo-Password-1"
function Api($Method, $Path, $Body = $null, $Headers = $H) {
    $p = @{ Method = $Method; Uri = "$B$Path"; Headers = $Headers
            ContentType = "application/json; charset=utf-8" }
    if ($null -ne $Body) {
        $p.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10))
    }
    try { Invoke-RestMethod @p } catch { ($_.ErrorDetails.Message | ConvertFrom-Json).error }
}
function Login($Email) {
    $t = Api POST "/auth/login" @{ email = $Email; password = $Pwd } @{}
    @{ Authorization = "Bearer $($t.access_token)" }
}
function Now([int]$Seconds = 0) { (Get-Date).ToUniversalTime().AddSeconds($Seconds).ToString("o") }
$Confirm = @{ confirmation = @{ method = "password"; value = $Pwd } }

$H = Login "owner@oberih.local"
$F = (Api GET "/facilities").items[0]
$FID = $F.id
$F.mode                                     # armed_away (демо-дані)
```

Токен демо-вузла видається один раз, тому для показу видамо новий:

```powershell
$Node = (Api GET "/facilities/$FID/nodes")[0]
$Dev = @{ "X-Device-Token" = (Api POST "/facilities/$FID/nodes/$($Node.id)/commission").device_token }
function Send($Events) { Api POST "/device/events" @{ events = $Events } $Dev }
# Канали демо-вузла: 1 — геркон дверей, 2 — геркон вікна, 3 — PIR вітальні, 4 — тампер
```

## 1. Подія, дублікат, рівні тривоги

```powershell
# Геркон дверей під охороною: C = 0,5 -> тривога рівня alarm, затримка входу
Send @(@{ channel = 1; event_type = "opened"; seq = 1; occurred_at = (Now) })
(Api GET "/facilities/$FID").mode           # entry_delay

# Той самий пакет ще раз (буфер після відновлення зв'язку) -> duplicate
Send @(@{ channel = 1; event_type = "opened"; seq = 1; occurred_at = (Now) })

# Інший seq, але через 3 с (< Δ(дубл.) = 5 с) -> теж duplicate
Send @(@{ channel = 1; event_type = "opened"; seq = 2; occurred_at = (Now 3) })

# Рух у вітальні в межах 60 с: C = 0,5 + 0,4 = 0,9 -> confirmed
Send @(@{ channel = 3; event_type = "motion"; seq = 3; occurred_at = (Now 10) })
(Api GET "/facilities/$FID/alarms?status=open").items | Select-Object level, confidence, status
```

## 2. Таймер затримки входу

Затримка входу — 30 с. Нічого не робимо, фоновий виконавець переведе об'єкт
у тривогу:

```powershell
Start-Sleep -Seconds 35
(Api GET "/facilities/$FID").mode           # alarm
(Api GET "/facilities/$FID/arming-log").items | Select-Object -First 3 from_mode, to_mode, source
```

## 3. Зняття з охорони та скасування тривоги

```powershell
# Закриття тривоги як хибної знімає об'єкт з охорони (повторне підтвердження)
$Alarm = (Api GET "/facilities/$FID/alarms?status=open").items[0]
Api POST "/alarms/$($Alarm.id)/acknowledge" (@{ action = "mark_false"; comment = "Перевірка" } + $Confirm)
(Api GET "/facilities/$FID").mode           # disarmed

# Законний вхід: постановка без затримки виходу, спрацювання, зняття в затримці
Api PUT "/facilities/$FID/settings" @{ exit_delay_s = 0 }
Api POST "/facilities/$FID/arm" @{ mode = "away" }
Send @(@{ channel = 1; event_type = "opened"; seq = 10; occurred_at = (Now) })
Api POST "/facilities/$FID/disarm" $Confirm   # mode = disarmed
(Api GET "/facilities/$FID/alarms").items[0].status   # cancelled

# Режим «Вдома»: рух не обробляється, геркон — затримка входу
Api POST "/facilities/$FID/arm" @{ mode = "home" }
Send @(@{ channel = 3; event_type = "motion"; seq = 11; occurred_at = (Now) })
(Api GET "/facilities/$FID").mode           # armed_home
Api POST "/facilities/$FID/disarm" $Confirm
```

## 4. Статистика хибних спрацювань (FAR)

```powershell
# У демо-даних 3 закриті тривоги дверей (2 хибні) + 1 позначена в кроці 3.
# Рекомендація з'являється, якщо N ≥ far_min_alarms (5); для показу знизимо до 3.
Api PUT "/facilities/$FID/settings" @{ far_min_alarms = 3 }
$S = Api GET "/facilities/$FID/statistics/false-alarms?tz=Europe/Kyiv"
$S.sensors | Select-Object sensor_name, alarms, false_alarms, far, recommendation, recommendation_text
$S.hours
```

## 5. Тестовий сценарій

```powershell
$Sc = (Api GET "/facilities/$FID/scenarios")[0]
$Sc.name
Api POST "/facilities/$FID/scenarios/$($Sc.id)/run" @{ mode = "armed_away" }  # passed = True
# Знятий з охорони об'єкт: геркон лише архівується, очікуваної тривоги немає
Api POST "/facilities/$FID/scenarios/$($Sc.id)/run" @{ mode = "disarmed" }    # passed = False, mismatches
# Реальні події об'єкта від запуску не змінилися:
(Api GET "/facilities/$FID/events").total
```

## 6. Резервна копія та відновлення

```powershell
$A = Login "admin@oberih.local"
$Bk = Api POST "/admin/backups" @{ kind = "full" } $A
$Bk | Select-Object file_name, size_bytes, sha256, status

Api POST "/facilities/$FID/zones" @{ name = "Гараж"; zone_type = "perimeter" }
(Api GET "/facilities/$FID/zones").name     # є «Гараж»

Api POST "/admin/backups/$($Bk.id)/restore" @{} $A          # reauth_required
Api POST "/admin/backups/$($Bk.id)/restore" $Confirm $A     # rows за таблицями
$H = Login "owner@oberih.local"              # сесії не входять у копію
(Api GET "/facilities/$FID/zones").name     # «Гаража» немає

# Експорт налаштувань і перевірка імпорту без запису
$Doc = Api GET "/facilities/$FID/export"
Api POST "/facilities/$FID/import?dry_run=true" $Doc
```

## 7. Сертифікати вузла

```powershell
$A = Login "admin@oberih.local"
(Api GET "/admin/certificates" $null $A).items | Select-Object serial_number, status, not_after
$New = Api POST "/admin/certificates" @{ node_id = $Node.id; days = 30 } $A
$New.private_key_pem                         # ключ показується лише один раз
Api GET "/admin/certificates/expiring?days=60" $null $A   # 30-денний сертифікат

# Відкликаємо всі чинні сертифікати вузла -> вузол не проходить перевірку
(Api GET "/admin/certificates?status=active&node_id=$($Node.id)" $null $A).items |
    ForEach-Object { Api POST "/admin/certificates/$($_.id)/revoke" $Confirm $A | Out-Null }
Api POST "/device/heartbeat" @{} $Dev        # certificate_invalid
(Api GET "/admin/certificates/crl" $null $A).revoked_serials

# Поновлення повертає вузлу доступ
Api POST "/admin/certificates/$($New.certificate.id)/renew" @{ days = 365 } $A | Out-Null
Api POST "/device/heartbeat" @{} $Dev        # server_time, poll_interval_s
```

## 8. Локалізація, часовий пояс, одиниці

```powershell
# Мова помилок: заголовок Accept-Language
Api GET "/facilities/00000000-0000-0000-0000-000000000000" $null ($H + @{ "Accept-Language" = "en" })
Api GET "/facilities/00000000-0000-0000-0000-000000000000"

# Місцевий час, 12-годинний формат, англійська система одиниць
Api PATCH "/users/me" @{ time_format = "12h"; measurement_system = "imperial" }
Send @(@{ channel = 2; event_type = "opened"; seq = 20; occurred_at = (Now)
          payload = @{ temperature_c = 21.5 } })
(Api GET "/facilities/$FID/events?limit=1&tz=America/New_York").items |
    Select-Object occurred_at, time_local, time_local_text, measurements

# CSV подій: українська (роздільник ;) та англійська (,)
Invoke-WebRequest "$B/facilities/$FID/events/export?locale=uk&tz=Europe/Kyiv" -Headers $H -OutFile events-uk.csv
Invoke-WebRequest "$B/facilities/$FID/events/export?locale=en" -Headers $H -OutFile events-en.csv
Get-Content events-uk.csv -Encoding UTF8 -TotalCount 3

# Мови з напрямом тексту та відомості про дані (GDPR)
Api GET "/locales" $null @{}
(Api GET "/privacy" $null @{ "Accept-Language" = "en" }).rights
```

## 9. Адміністрування користувачів і даних

```powershell
$A = Login "admin@oberih.local"
$Guest = (Api GET "/admin/users" $null $A).items | Where-Object email -eq "guest@oberih.local"
Api POST "/admin/users/$($Guest.id)/block" $null $A | Select-Object email, blocked_at
Api POST "/auth/login" @{ email = "guest@oberih.local"; password = $Pwd } @{}   # account_blocked
Api POST "/admin/users/$($Guest.id)/unblock" $null $A | Out-Null
Api GET "/admin/stats" $null $A
Api POST "/admin/data/purge" $Confirm $A
(Api GET "/admin/audit-log?limit=10" $null $A).items | Select-Object action, entity_type, created_at
```

## 10. Хронологія інциденту (професійний тариф)

```powershell
$Last = (Api GET "/facilities/$FID/alarms").items | Where-Object status -ne "cancelled" | Select-Object -First 1
$Sum = Api POST "/alarms/$($Last.id)/summary"
$Sum.facts
$Sum.assumptions
```
