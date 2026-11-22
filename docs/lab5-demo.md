# Демонстрація ЛБ5: розгорнута система «Оберіг»

Один наскрізний сценарій на **розгорнутій** системі (Docker Compose + Nginx,
доступ через публічну HTTPS-адресу тунелю, а не `localhost`). Методичка
вимагає показати: бізнес-логіку; адміністрування серверної частини й
бізнес-логіки; налаштування IoT-клієнта; взаємодію IoT-клієнта й сервера.
Пункти 1–6 — блоки відео з таймкодами.

Потрібні: Docker Desktop, `bore.exe` (TCP-тунель), PlatformIO, VS Code з Wokwi.
Подробиці розгортання — [`deploy.md`](deploy.md).

## 1. Розгортання з нуля

```powershell
cd D:\ARK\oberih
git switch lab5
.\deploy\init-env.ps1                      # секрети в .env.prod (не в git)
.\deploy\make-dev-cert.ps1                 # сертифікат Nginx (localhost, bore.pub)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
docker compose -f docker-compose.prod.yml --env-file .env.prod logs migrate   # 0001..0004, центр сертифікації
$C = "-f", "docker-compose.prod.yml", "--env-file", ".env.prod"
docker compose @C exec -e SEED_PASSWORD=Demo-Password-1 api python -m scripts.seed
.\deploy\smoke-test.ps1 -BaseUrl https://localhost -Password Demo-Password-1 -SkipCertificateCheck
```

Показати: чотири сервіси (`db`, `migrate` завершився, `api` і `nginx`
healthy), smoke-тест 14/14 і `http://localhost` -> 301 на HTTPS.

Окреме вікно — публічна адреса. TCP-тунель bore пересилає байти на HTTPS
Nginx, TLS завершує сам Nginx (тунелі, що завершують TLS самі, для вузла у
Wokwi не годяться — припущення 50б):

```powershell
& "$env:LOCALAPPDATA\Programs\bore\bore.exe" local 443 --to bore.pub   # -> bore.pub:<порт>
```

Секрети вузла для цієї адреси (вузол довірятиме сертифікату Nginx) та
збирання прошивки:

```powershell
$Url = "https://bore.pub:<порт>"
docker compose @C cp deploy/certs/server.crt api:/data/nginx.crt
docker compose @C exec api python -m scripts.provision_node --server-url $Url --ca-file /data/nginx.crt --output /data/secrets.h
docker compose @C cp api:/data/secrets.h iot/include/secrets.h
docker compose @C exec api rm /data/secrets.h /data/nginx.crt
cd iot; pio run -e esp32dev; cd ..
```

Допоміжні функції працюють через публічну адресу. Windows PowerShell 5.1
довіряє лише сертифікату нашого Nginx (перевірка за відбитком):

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]12288
Add-Type @"
using System.Net; using System.Security.Cryptography.X509Certificates;
public static class OberihPin {
    public static string Thumb;
    public static void Install(string thumb) {
        Thumb = thumb;
        ServicePointManager.ServerCertificateValidationCallback =
            (s, c, ch, e) => c != null && c.GetCertHashString() == Thumb;
    }
}
"@
[OberihPin]::Install((New-Object Security.Cryptography.X509Certificates.X509Certificate2 "D:\ARK\oberih\deploy\certs\server.crt").Thumbprint)
$B = "$Url/api/v1"
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
$Confirm = @{ confirmation = @{ method = "password"; value = $Pwd } }
$H = Login "owner@oberih.local"
$A = Login "admin@oberih.local"
$FID = (Api GET "/facilities").items[0].id
$NID = (Api GET "/facilities/$FID/nodes")[0].id
function Mode { (Api GET "/facilities/$FID").mode }
function Commands {
    Api GET "/facilities/$FID/nodes/$NID/commands" |
        Select-Object -First 5 command_type, status, nonce | Format-Table
}
Api GET "/health"                          # status ok, database ok
```

## 2. Вузол у Wokwi підключається до розгорнутої системи

У VS Code: `iot/diagram.json` -> F1 -> *Wokwi: Start Simulator*. У Serial
Monitor:

```
[wifi] connected
[clock] synced with server: 2026-...Z      <- server_epoch із heartbeat
[config] applied version 1 from heartbeat
[cmd] executed arm_away -> armed_away      <- об'єкт під охороною (демо-дані)
```

```powershell
(Api GET "/facilities/$FID/nodes")[0] | Select-Object status, firmware_version, last_seen_at
Commands                                   # arm_away acked
```

Подія геркона: перемкніть `1 Door`. Вузол — `entry_delay`, подія надіслана
(`accepted 1`); на сервері — тривога рівня `alarm`, C(t) = 0,5:

```powershell
Mode                                       # entry_delay
(Api GET "/facilities/$FID/alarms?status=open").items | Select-Object level, confidence
```

Рух у `3 PIR` протягом 60 с додає другий датчик: C(t) = 0,9 -> `confirmed`.
Дублікат: та сама подія вдруге не створює нової (показано в smoke-тесті й
у пункті 4).

## 3. Налаштування IoT-клієнта й команди сервера

Зняття тривоги командою сервера (підпис HMAC, nonce, строк 60 с):

```powershell
Api POST "/facilities/$FID/disarm" $Confirm
Commands                                   # disarm: pending -> delivered -> acked
```

Вузол: `[cmd] executed disarm -> disarmed`, зелений світлодіод.

Налаштування із сервера (`set_config`, версія конфігурації):

```powershell
Api PATCH "/facilities/$FID/nodes/$NID" @{ debounce_ms = 80 } | Select-Object debounce_ms, config_version
Api PUT "/facilities/$FID/settings" @{ exit_delay_s = 15 } | Select-Object exit_delay_s
```

Вузол: `[config] applied version 2 from command`, потім версія 3; `get`
показує нові значення. Зміна з консолі: `set pir_lockout 5`, `save`, `get`;
невалідне значення `set debounce_ms 5` відхиляється.

Підроблена команда: `sim badcmd` -> `bad_signature, mode stays ...`.

## 4. Втрата зв'язку й відновлення

Консоль вузла: `net off`. Після трьох невдалих heartbeat — синій спалах і
сигнал зумера. Перемкніть `2 Window` двічі з паузою понад 5 с, потім `buffer`
— події чекають у NVS-буфері з seq і часом.

Через 90 с сервер позначає вузол недоступним:

```powershell
(Api GET "/facilities/$FID/nodes")[0].status        # offline
```

`net on`: `connection restored`, пакет `[events] sent 2: accepted 2,
duplicates 0`. На сервері — події з початковим часом `occurred_at` і
`node_offline` / `node_online`:

```powershell
(Api GET "/facilities/$FID/events?limit=6").items | Select-Object event_type, seq, occurred_at, received_at | Format-Table
```

## 5. Адміністрування

```powershell
# Користувачі
(Api GET "/admin/users" $null $A).items | Select-Object email, is_active, blocked_at | Format-Table
# Резервна копія застосунку й відновлення
$Bk = Api POST "/admin/backups" @{ kind = "full" } $A
Api POST "/admin/backups/$($Bk.id)/restore" $Confirm $A
# Копія тому БД і перевірка відновлення
.\deploy\backup-db.ps1 backup
.\deploy\backup-db.ps1 verify
# Експорт налаштувань об'єкта
(Api GET "/facilities/$FID/export").nodes | Select-Object serial, name
# Сертифікат вузла: випуск і відкликання
$Cert = Api POST "/admin/certificates" @{ node_id = $NID; days = 30 } $A
Api POST "/admin/certificates/$($Cert.certificate.id)/revoke" $Confirm $A | Select-Object status
```

Після відновлення повної копії токен вузла з копії залишається чинним (хеш
токена входить у копію).

## 6. Локалізація, інтернаціоналізація, GDPR

Кроки розділів 8 і 9 з [`lab3-demo.md`](lab3-demo.md) з тими самими
функціями (`$B` тепер — публічна адреса): мова помилок за `Accept-Language`,
місцевий час і формати, CSV подій для `uk`/`en`, `/privacy`, блокування й
анонімізація користувача.

Обмеження частоти: десяток швидких спроб входу дає `429` (Nginx), а потік
вузла — ні:

```powershell
1..12 | ForEach-Object { try { (Invoke-WebRequest "$B/auth/login" -Method POST -ContentType application/json -Body '{"email":"x@y.z","password":"x"}' -UseBasicParsing).StatusCode } catch { [int]$_.Exception.Response.StatusCode } }
```

## Поза межами демонстрації

Vision & Scope (розділ 2.2) передбачає також веб-клієнт і застосунок
Android. До цього завдання вони не входять: усі функції показано через REST
API, а IoT-вузол — у симуляції Wokwi.
