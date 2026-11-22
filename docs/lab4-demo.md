# Демонстрація ЛБ4: IoT-клієнт (ESP32 у Wokwi)

Покрокова інструкція для показу й запису відео. Відео має два блоки:
**А — бізнес-логіка вузла** і **Б — функції налаштування**. Таймкоди для
опису відео зручно ставити на початку кожного пункту (А1, А2, … Б1, …).

Потрібні три вікна PowerShell (сервер, тунель, команди) і VS Code з
розширенням Wokwi. Вузол у Wokwi бачить лише публічні адреси інтернету
(`host.wokwi.internal` працює тільки з платним приватним шлюзом), тому
сервер відкривається через тимчасовий тунель Cloudflare.

## 0. Підготовка

Чиста база й демо-дані (`down -v` **видаляє всі дані** локальної БД):

```powershell
cd D:\ARK\oberih
docker compose down -v
docker compose up -d db
cd server
.venv\Scripts\Activate.ps1
alembic upgrade head
python -m scripts.init_ca
$env:SEED_PASSWORD = "Demo-Password-1"
python -m scripts.seed
```

Вікно 1 — сервер:

```powershell
cd D:\ARK\oberih\server
.venv\Scripts\Activate.ps1
uvicorn app.main:app
```

Вікно 2 — тунель (один раз: `winget install Cloudflare.cloudflared`). Команда
виводить адресу `https://<випадкові-слова>.trycloudflare.com`:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Вікно 3 — секрети вузла і збирання прошивки. Скрипт видає демо-вузлу новий
токен і ключ підпису команд, визначає сертифікат-якір TLS тунелю (видавця
сертифіката тунелю, припущення 50) й записує
все в `iot/include/secrets.h`:

```powershell
cd D:\ARK\oberih\server
.venv\Scripts\Activate.ps1
python -m scripts.provision_node --server-url https://<адреса-тунелю>
cd ..\iot
pio run -e esp32dev
```

Допоміжні функції (у тому самому вікні 3):

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
$Confirm = @{ confirmation = @{ method = "password"; value = $Pwd } }
$H = Login "owner@oberih.local"
$FID = (Api GET "/facilities").items[0].id
$NID = (Api GET "/facilities/$FID/nodes")[0].id
function Mode { (Api GET "/facilities/$FID").mode }
function Commands {
    Api GET "/facilities/$FID/nodes/$NID/commands" |
        Select-Object -First 5 command_type, status, nonce, payload | Format-Table
}
function Events($N = 5) {
    (Api GET "/facilities/$FID/events?limit=$N").items |
        Select-Object seq, event_type, occurred_at, received_at | Format-Table
}
Mode                                       # armed_away (демо-дані)
```

У VS Code відкрийте **папку** `D:\ARK\oberih\iot` (File → Open Folder:
Wokwi шукає `wokwi.toml` у корені відкритої папки), відкрийте `diagram.json`
і запустіть **F1 → Wokwi: Start Simulator**. Консоль вузла — вкладка
**Terminal** під схемою; команди вводяться прямо в неї. Після кожного
`pio run` симулятор треба перезапустити (Stop -> Start), інакше працює
попередня прошивка. Вікно VS Code із симулятором тримайте **видимим**: у фоні Wokwi
ставить симуляцію на паузу (таймер зупиняється, кнопка ▶ стає жовтою), і
вузол перестає надсилати heartbeat. Той самий Serial доступний і через TCP `localhost:4000`
(RFC 2217, `rfc2217ServerPort` у `wokwi.toml`). Канали: перемикач `1 Door` — двері, `2 Window` —
вікно, `4 Tamper` — корпус, датчик `3 PIR` — рух (кнопка на датчику в
симуляції).

## Блок А. Бізнес-логіка

### А1. Автоматичні тести логіки

```powershell
cd D:\ARK\oberih\iot
pio test -e native          # 65 тестів: фільтр, PIR, автомат, буфер, повтори, підпис
cd ..\server
pytest tests/test_commands.py -v
```

### А2. Підключення, синхронізація часу, узгодження режиму

У Serial Monitor після старту:

```
[wifi] connected
[clock] synced with server: 2026-11-21T...Z
[cmd] executed arm_away -> armed_away
```

Об'єкт на сервері під охороною, а вузол запустився у стані «знято». Сервер
— джерело істини: на heartbeat із `mode = disarmed` він ставить підписану
команду `arm_away`, вузол перевіряє підпис і переходить у режим сервера.
Світлодіод стає червоним. У вікні 3:

```powershell
Commands                                   # arm_away  acked
```

Консольна команда `status` показує режим, синхронізований час, стан
буфера й кількість рукопожатть TLS (`tls handshakes: 1` після кількох
heartbeat означає, що з'єднання використовується повторно).

### А3. Фільтр брязкоту (ІК-2)

У консолі:

```
sim bounce 1
```

Очікувано: `[debounce] ch1: 9 toggles in 45 ms, accepted changes 0`. Серія
перемикань коротша за `debounce_ms` (50 мс) і подій не створює.

### А4. Подія геркона -> затримка входу -> тривога на сервері

Перемкніть `1 Door` (двері відчинено). У консолі:

```
[event] seq=1 ch=1 opened mode=entry_delay ALARM
[events] sent 1: accepted 1, duplicates 0, left 0
```

Світлодіод мигає (затримка входу). На сервері:

```powershell
Mode                                       # entry_delay
(Api GET "/facilities/$FID/alarms?status=open").items | Select-Object level, confidence
Events
```

Через 30 с (`entry_delay_s`) і вузол, і сервер переходять у `alarm`
незалежно один від одного: світлодіод мигає часто, звучить зумер.
Поверніть перемикач (`closed`).

### А5. Зняття з охорони командою сервера (ІК-7)

```powershell
Api POST "/facilities/$FID/disarm" $Confirm
Commands                                   # disarm  pending -> delivered -> acked
```

Протягом інтервалу опитування (до 30 с) у консолі з'являється
`[cmd] executed disarm -> disarmed`, світлодіод стає зеленим.

### А6. Відхилення підробленої команди

```
sim badcmd
```

Очікувано: `forged disarm: bad_signature, mode stays disarmed`. Перевірку
простроченої команди й повторного nonce показують тести А1
(`test_expired_timestamp_is_rejected`, `test_repeated_nonce_is_rejected`).

### А7. Блокування PIR (ІК-3) і тампер

```powershell
Api POST "/facilities/$FID/arm" @{ mode = "away" }   # постановка; вузол отримає команду
```

Після команди й затримки виходу (30 с) натисніть на `3 PIR` -> **Simulate
motion**, а через **6–8 с** — ще раз. У Wokwi вихід датчика після
спрацювання тримається в HIGH ~5 с (`delayTime`), і повторне натискання в
цей час лише подовжує сигнал без нового фронту, тож друге натискання має
бути після спаду виходу, але в межах 10 с блокування:

```
[event] seq=... ch=3 motion mode=entry_delay ALARM
[pir] motion ignored (lockout 10 s)
```

Тампер дає тривогу в будь-якому режимі: зніміть охорону (`disarm`), потім
перемкніть `4 Tamper` — `mode=alarm`, на сервері рівень `confirmed`.
Поверніть перемикач (`tamper_restored`) і зніміть тривогу:

```powershell
Api POST "/facilities/$FID/disarm" $Confirm
```

### А8. Втрата зв'язку: буфер, індикація, пакет після відновлення (ІК-4…ІК-6)

У консолі:

```
net off
```

Після трьох невдалих heartbeat (кілька секунд, повтори 1 с, 2 с, 4 с…)
`[net] server unreachable: offline indication on`: синій спалах щосекунди й
короткий сигнал кожні 10 с. Перемкніть `1 Door` і `2 Window` кілька разів:
події лягають у буфер.

```
buffer
status
```

Через 90 с без зв'язку сервер фіксує `node_offline`:

```powershell
(Api GET "/facilities/$FID/nodes")[0].status       # offline
```

Відновлення:

```
net on
```

Очікувано: `connection restored` (синій постійно 3 с), потім
`[events] sent N: accepted …, duplicates …, left 0`. Дублікатами сервер
вважає повтори того самого датчика й типу ближче ніж за 5 с, тому для
наочності перемикайте не частіше ніж раз на 5 с. Події мають початкові
мітки часу (`occurred_at` раніше за `received_at`), сервер записав
`node_online`:

```powershell
Events 10
(Api GET "/facilities/$FID/nodes")[0].status       # online
```

## Блок Б. Налаштування (ІК-8)

### Б1. Консоль вузла (заміна BLE у симуляції, ЗЛ-1)

```
get
set exit_delay 20
set debounce_ms 5
set debounce_ms 80
save
get
```

`set debounce_ms 5` відхиляється (`value is out of range`, межі 10–1000).
Після `save` значення зберігаються в NVS. `defaults` повертає значення за
замовчуванням (адреса сервера не скидається).

### Б2. Зміна налаштувань вузла із сервера (set_config)

```powershell
Api PATCH "/facilities/$FID/nodes/$NID" @{ debounce_ms = 60; pir_lockout_s = 5 } |
    Select-Object debounce_ms, pir_lockout_s, config_version
Commands                                   # set_config
```

У консолі за наступного heartbeat: `[config] applied version 2 from command`.
Команда `get` показує `debounce_ms = 60`, `pir_lockout = 5`. Невалідне
значення сервер не прийме (`422`):

```powershell
Api PATCH "/facilities/$FID/nodes/$NID" @{ debounce_ms = 5000 }
```

### Б3. Затримки об'єкта -> конфігурація вузла

```powershell
Api PUT "/facilities/$FID/settings" @{ exit_delay_s = 10 }
```

Вузол отримує версію 3 (`get`: `exit_delay = 10`). Постановка `away` тепер
має 10-секундну затримку виходу й на сервері, і на вузлі.

## Підсумок перевірок

| Що показано | Пункт |
|---|---|
| Автомат режимів працює автономно й узгоджується із сервером (ІК-1) | А2, А4, А8 |
| Фільтр брязкоту (ІК-2) | А3, А1 |
| Блокування PIR (ІК-3) | А7, А1 |
| Буфер у NVS, наскрізний seq, пакет після відновлення (ІК-4) | А8, А1 |
| HTTPS і повтори зі зростаючою затримкою (ІК-5) | А8, А1 |
| Індикація режимів і втрати зв'язку (ІК-6) | А2–А8 |
| Підписані команди: підпис, час, nonce (ІК-7) | А2, А5, А6, А1 |
| Налаштування з консолі й сервера (ІК-8) | Б1–Б3 |
