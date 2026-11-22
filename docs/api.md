# REST API «Оберіг» (версія 1)

Повна машинозчитувана специфікація — [`openapi.json`](openapi.json) (OpenAPI 3,
генерується FastAPI командою `python -m scripts.export_openapi`). Інтерактивна
документація після запуску сервера: <http://localhost:8000/docs>.

## Загальні правила

| Правило | Опис |
|---|---|
| Префікс | Усі шляхи починаються з `/api/v1` |
| Формат | JSON у запитах і відповідях (`Content-Type: application/json`) |
| Час | UTC, ISO 8601 (`2026-10-25T22:04:37Z`). Час у запитах має містити зсув (наприклад, `+03:00`) |
| Автентифікація користувача | `Authorization: Bearer <access_token>` — JWT на 15 хв; оновлення через `/auth/refresh` |
| Автентифікація пристрою | `X-Device-Token: <token>` — видається один раз під час введення вузла в експлуатацію |
| Мова повідомлень | Заголовок `Accept-Language` (`uk` за замовчуванням, `en`) |
| Пагінація | `?limit=20&offset=0` (`limit` від 1 до 100); відповідь `{items, total, limit, offset}` |
| Повторне підтвердження | Зняття з охорони та дії з тривогою вимагають `confirmation: {method: "password"\|"totp", value}` |

### Формат помилки

```json
{
  "error": {
    "code": "tariff_limit",
    "message": "Досягнуто ліміту об'єктів для вашого тарифного плану"
  }
}
```

Для помилок валідації (422) додається `details` зі списком полів. Коди помилок
і переклади зібрано в `server/app/i18n.py`.

| HTTP | Коли |
|---|---|
| 400 | Дані коректні за форматом, але неприйнятні (`invalid_timezone`, `unknown_channel`, …) |
| 401 | Немає або недійсний токен; не пройдено повторне підтвердження |
| 403 | Немає права за роллю, не діє гостьовий доступ, обмеження тарифу |
| 404 | Ресурс не існує або належить об'єкту, учасником якого користувач не є |
| 409 | Конфлікт стану: недопустимий перехід режиму, дублікат, тривогу вже закрито |
| 422 | Помилка валідації запиту |

## Ендпоінти

### Сервіс і довідники

| Метод | Шлях | Призначення | Доступ |
|---|---|---|---|
| GET | `/health` | Стан сервісу й з'єднання з БД (`503 service_unavailable`, якщо БД недоступна) | усі |
| GET | `/tariffs` | Тарифні плани | усі |

### Автентифікація (`auth`)

| Метод | Шлях | Призначення |
|---|---|---|
| POST | `/auth/register` | Реєстрація (потрібна `privacy_consent: true`), тариф `basic` |
| POST | `/auth/login` | Вхід; за увімкненої 2FA — ще `totp_code` |
| POST | `/auth/refresh` | Нова пара токенів; старий refresh-токен відкликається |
| POST | `/auth/logout` | Відкликання refresh-токена |
| POST | `/auth/totp/enable` | Секрет і посилання `otpauth://` для автентифікатора |
| POST | `/auth/totp/verify` | Перевірка першого коду, увімкнення 2FA |

### Профіль (`users`)

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/users/me` | Профіль і тариф |
| PATCH | `/users/me` | Ім'я, мова, часовий пояс, система мір |
| GET | `/users/me/export` | Експорт персональних даних (GDPR) |
| DELETE | `/users/me` | Знеособлення облікового запису (тіло: `password`) |

### Об'єкти та учасники (`facilities`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities` | Об'єкти користувача | учасник |
| POST | `/facilities` | Створення (ліміт за тарифом) | будь-який користувач |
| GET | `/facilities/{id}` | Об'єкт і режим охорони | усі ролі |
| PATCH, DELETE | `/facilities/{id}` | Зміна, видалення з усіма даними | власник |
| GET | `/facilities/{id}/settings` | Затримки, вікна, ваги, пороги | усі ролі |
| PUT | `/facilities/{id}/settings` | Зміна параметрів | власник, монтажник |
| GET, POST | `/facilities/{id}/members` | Учасники, додавання за email | власник |
| PATCH, DELETE | `/facilities/{id}/members/{member_id}` | Роль, період доступу, вилучення | власник |

### Обладнання (`equipment`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/zones` | Зони | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/zones[/{zone_id}]` | Керування зонами | власник, монтажник |
| GET | `/facilities/{id}/nodes[/{node_id}]` | Вузли та стан зв'язку | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/nodes[/{node_id}]` | Реєстрація, зміна (назва, `debounce_ms` 10–1000, `pir_lockout_s` 0–600), видалення вузла | власник, монтажник |
| POST | `/facilities/{id}/nodes/{node_id}/commission` | Видача токена пристрою й ключа підпису команд (один раз) | власник, монтажник |
| GET | `/facilities/{id}/nodes/{node_id}/commands` | Останні 50 команд вузла та стан доставки | власник, монтажник |
| GET | `/facilities/{id}/nodes/{node_id}/sensors` | Датчики вузла | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/nodes/{node_id}/sensors[/{sensor_id}]` | Керування датчиками | власник, монтажник |

### Розклади (`schedules`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/schedules` | Розклади | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/schedules[/{schedule_id}]` | Керування розкладами | власник, монтажник |

Розклад (`action`: `arm_away`, `arm_home`, `disarm`; `days_mask`: біт 0 —
понеділок … біт 6 — неділя; `local_time` — місцевий час об'єкта) виконує
фоновий виконавець. Поле `last_run_at` у відповіді — останній виконаний
запуск (UTC). Правила (вікно 10 хв, без зняття під час тривоги) — у
припущенні 59.

### Охорона (`arming`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| POST | `/facilities/{id}/arm` | `{"mode": "away"\|"home"}` | власник, член родини, гість (у межах часу) |
| POST | `/facilities/{id}/disarm` | Зняття з повторним підтвердженням; з режиму `alarm` — лише хто може підтверджувати тривоги | те саме |
| GET | `/facilities/{id}/arming-log` | Журнал: хто, коли, з якого режиму, звідки | власник, член родини, гість |

Автомат режимів (рисунок 2 Vision & Scope, `app/services/state_machine.py`):

```
disarmed    --arm away-->              exit_delay   (exit_delay_s = 0: armed_away)
disarmed    --arm home-->              armed_home
exit_delay  --минула затримка-->       armed_away   (фоновий виконавець)
armed_*     --спрацювання-->           entry_delay  (entry_delay_s = 0: alarm)
entry_delay --минула затримка-->       alarm        (фоновий виконавець)
будь-який   --тампер / цілодобова-->   alarm
exit_delay | armed_* | entry_delay | alarm --disarm--> disarmed
```

Інші переходи дають `409 invalid_transition`. Зняття під час затримки входу
скасовує тривогу (`cancelled`); закриття останньої тривоги (`resolve`,
`mark_false`) знімає об'єкт з охорони.

### Пристрій (`device`)

| Метод | Шлях | Призначення |
|---|---|---|
| POST | `/device/events` | Пакет до 200 подій `{channel, event_type, seq, occurred_at, payload}` |
| POST | `/device/heartbeat` | Службове повідомлення; підтвердження команд; відповідь — час, режим, підписані команди, конфігурація вузла |

#### Heartbeat і команди вузлу (ЛБ4, ІК-7, ІК-8)

Усі нові поля необов'язкові: старий запит `{}` або `{"firmware_version": "…"}`
обробляється як раніше, а старі поля відповіді не змінилися.

```http
POST /api/v1/device/heartbeat
X-Device-Token: <token>

{"firmware_version": "0.4.0", "mode": "disarmed", "config_version": 2,
 "buffer_depth": 0, "acked_command_ids": ["4b0c…"]}
```

```json
{"server_time": "2026-11-21T12:00:00Z", "poll_interval_s": 30,
 "facility_mode": "armed_home", "server_epoch": 1795262400, "last_seq": 41,
 "config": {"exit_delay_s": 30, "entry_delay_s": 30, "poll_interval_s": 30,
            "debounce_ms": 80, "pir_lockout_s": 10, "config_version": 3},
 "commands": [{"id": "9d2e…", "type": "arm_home",
               "payload": "{\"mode\":\"armed_home\"}",
               "nonce": 1795262399517, "issued_at": 1795262399,
               "expires_at": 1795262459, "signature": "5f1a…"}]}
```

- **Черга команд.** Постановка й зняття (`/arm`, `/disarm`) ставлять усім
  вузлам об'єкта команду `arm_away`, `arm_home` або `disarm` із
  `payload = {"mode": <новий режим>}`. Зміна `debounce_ms`, `pir_lockout_s`
  вузла або `exit_delay_s`, `entry_delay_s`, `poll_interval_s` об'єкта
  збільшує `config_version` і ставить команду `set_config` із повною
  конфігурацією.
- **Підпис:** `HMAC-SHA256(command_key, "<node_id>|<nonce>|<type>|<payload>|<issued_at>")`
  у hex. `payload` — рядок канонічного JSON (без пробілів, ключі за абеткою);
  вузол перевіряє підпис саме над цим рядком. Час — секунди Unix.
- **Доставка:** команда видається в кожній відповіді heartbeat, доки вузол не
  передасть її `id` в `acked_command_ids`, але не довше за строк дії 60 с
  (потім стан `expired`). Чужі `id` в підтвердженнях ігноруються.
- **Одноразове число** строго зростає в межах вузла: більше з (останнє + 1)
  і поточного часу в мілісекундах.
- **Узгодження режиму.** Якщо вузол повідомляє `mode`, що не відповідає
  режиму об'єкта (`exit_delay` і `armed_away` вважаються узгодженими), у
  буфері вузла немає подій (`buffer_depth = 0`) і немає відкритої команди,
  сервер ставить команду, що приводить вузол до свого режиму. Затримку входу
  й тривогу сервер не нав'язує — їх вузол формує сам за датчиками.
- **`last_seq`** — найбільший порядковий номер подій вузла в архіві; вузол із
  очищеною NVS продовжує нумерацію після нього.

Конвеєр обробки (`app/services/pipeline/`): подія — дублікат, якщо в архіві є
та сама подія датчика з тим самим `seq` або з різницею в часі менше за
Δ(дубл.) (`duplicate_window_s`, 5 с). Відповідь містить статус кожної події:

```json
{"accepted": 1, "duplicates": 1, "last_seq": 42,
 "results": [{"seq": 41, "channel": 1, "status": "duplicate"},
             {"seq": 42, "channel": 2, "status": "accepted"}]}
```

Далі: відсів за режимом і зоною, індекс достовірності
C(t) = Σ w(i) по різних датчиках у вікні Δ(підтв.) (60 с), рівень `warning` /
`alarm` (C ≥ 0,4) / `confirmed` (C ≥ 0,9; тампер і цілодобова зона — завжди),
створення або підвищення рівня поточної тривоги, перехід автомата. Пакет із
невідомим каналом відхиляється цілком (`400 unknown_channel`). Вузол із
відкликаним або простроченим сертифікатом отримує `401 certificate_invalid`.

Приклад:

```http
POST /api/v1/device/events
X-Device-Token: <token>

{"events": [
  {"channel": 1, "event_type": "opened", "seq": 41, "occurred_at": "2026-10-25T22:04:30Z"},
  {"channel": 3, "event_type": "motion", "seq": 42, "occurred_at": "2026-10-25T22:04:33Z",
   "payload": {"temperature_c": 21.5}}
]}
```

### Події та тривоги (`events`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/events?from=&to=&event_type=&zone_id=&tz=` | Архів подій (UTC, `time_local`, `time_local_text`, `measurements`) | власник, член родини, гість |
| GET | `/facilities/{id}/alarms?status=&level=&tz=` | Тривоги (`opened_at_local`) | власник, член родини, гість |
| POST | `/alarms/{alarm_id}/acknowledge` | `acknowledge`, `mark_false`, `resolve` з повторним підтвердженням | власник, член родини |
| POST | `/alarms/{alarm_id}/summary` | Стисла хронологія інциденту (професійний тариф) | власник, член родини, гість |
| GET | `/alarms/{alarm_id}/summaries` | Сформовані хронології | те саме |

### Аналітика (`analytics`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/statistics/false-alarms?tz=` | FAR за датчиками, зонами й годиною доби; `recommendation: check_sensor` | перегляд подій; тариф зі статистикою |
| GET, POST | `/facilities/{id}/scenarios` | Тестові сценарії `{steps: [{offset_ms, sensor_id, state}], expected: [{level, zone_id}]}` | власник, монтажник |
| GET, PATCH, DELETE | `/facilities/{id}/scenarios/{scenario_id}` | Керування сценарієм | власник, монтажник |
| POST | `/facilities/{id}/scenarios/{scenario_id}/run` | Відтворення в ізольованому режимі `{mode}` -> `{passed, actual, mismatches}` | власник, монтажник |
| GET | `/facilities/{id}/scenarios/{scenario_id}/runs` | Історія запусків | власник, монтажник |

### Перенесення даних (`transfer`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/export` | Документ налаштувань (`format_version`, природні ключі) | власник, монтажник |
| POST | `/facilities/{id}/import?dry_run=true` | Імпорт; `dry_run` лише показує зміни; помилки з `details.loc` | власник, монтажник |
| GET | `/facilities/{id}/events/export?format=csv&locale=&tz=&from=&to=` | CSV подій (UTF-8 з BOM, роздільник за локаллю) | перегляд подій |

### Адміністрування (`admin`, `certificates`)

Доступ лише для користувача з `is_platform_admin = true`; кожна дія
записується в журнал аудиту. Позначка «🔒» — потрібне повторне
підтвердження `{"confirmation": {"method": "password"|"totp", "value": "..."}}`.

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/admin/users`, `/admin/users/{id}` | Користувачі |
| POST | `/admin/users/{id}/block`, `/unblock` | Блокування (вхід і сесії) |
| PUT | `/admin/users/{id}/platform-admin` | Права адміністратора (крім останнього) |
| POST | `/admin/users/{id}/sessions/revoke` | Завершення всіх сесій |
| POST | `/admin/users/{id}/totp/reset` | Скидання двофакторної автентифікації |
| PUT | `/admin/users/{id}/tariff` | Зміна тарифу `{code}` |
| GET | `/admin/audit-log?user_id=&action=&entity_type=` | Журнал аудиту |
| GET | `/admin/stats` | Кількість записів і розмір архіву |
| POST 🔒 | `/admin/data/purge` | Видалення даних, старших за строк зберігання тарифу |
| POST, GET | `/admin/backups` | Створення `{kind: full\|settings}` і реєстр копій |
| GET | `/admin/backups/{id}/download` | Файл копії (gzip) |
| POST 🔒 | `/admin/backups/{id}/restore` | Відновлення в одній транзакції |
| DELETE 🔒 | `/admin/backups/{id}` | Видалення копії |
| POST, GET | `/admin/certificates?status=&node_id=&expires_before=` | Випуск сертифіката вузла (ключ — один раз) і перелік |
| GET | `/admin/certificates/{id}`, `/crl`, `/expiring?days=` | Сертифікат, відкликані номери, строк дії спливає |
| POST 🔒 | `/admin/certificates/{id}/revoke` | Відкликання |
| POST | `/admin/certificates/{id}/renew` | Поновлення (старий відкликається) |

### Довідники (`service`)

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/locales` | Мови: код, назва, напрям тексту `ltr`/`rtl`, чи підтримується |
| GET | `/privacy` | Відомості про оброблювані дані, права та строки зберігання |

## Архітектура серверної частини

```
app/api/v1/*.py     маршрути: розбір запиту, перевірка прав, виклик сервісу
app/services/*.py   бізнес-логіка та робота з моделями (SQL лише тут)
app/models/*.py     моделі SQLAlchemy (таблиці БД)
app/schemas/*.py    схеми Pydantic запитів і відповідей
app/deps.py         залежності: сесія БД, поточний користувач, вузол, пагінація
app/errors.py       єдиний формат помилок; app/i18n.py — переклади
app/security.py     Argon2, JWT, токени пристроїв, TOTP
app/services/state_machine.py   автомат режимів (чистий модуль)
app/services/pipeline/core.py   ядро конвеєра: дублікати, відсів, C(t), рівні
app/services/pipeline/processor.py   обробка пакета вузла з БД
app/services/pipeline/simulator.py   відтворення сценаріїв у пам'яті
app/services/timers.py, app/worker.py   таймери та фоновий виконавець
app/l10n.py, app/units.py   місцевий час, формати, сортування, одиниці
```
