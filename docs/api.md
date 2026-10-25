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
| GET | `/health` | Стан сервісу | усі |
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
| POST, PATCH, DELETE | `/facilities/{id}/nodes[/{node_id}]` | Реєстрація, зміна, видалення вузла | власник, монтажник |
| POST | `/facilities/{id}/nodes/{node_id}/commission` | Видача токена пристрою (один раз) | власник, монтажник |
| GET | `/facilities/{id}/nodes/{node_id}/sensors` | Датчики вузла | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/nodes/{node_id}/sensors[/{sensor_id}]` | Керування датчиками | власник, монтажник |

### Розклади (`schedules`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/schedules` | Розклади | усі ролі |
| POST, PATCH, DELETE | `/facilities/{id}/schedules[/{schedule_id}]` | Керування розкладами | власник, монтажник |

### Охорона (`arming`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| POST | `/facilities/{id}/arm` | `{"mode": "away"\|"home"}` | власник, член родини, гість (у межах часу) |
| POST | `/facilities/{id}/disarm` | Зняття з повторним підтвердженням; з режиму `alarm` — лише хто може підтверджувати тривоги | те саме |
| GET | `/facilities/{id}/arming-log` | Журнал: хто, коли, з якого режиму, звідки | власник, член родини, гість |

Допустимі переходи (рисунок 2 Vision & Scope):

```
disarmed --away--> exit_delay --(минула затримка виходу)--> armed_away
disarmed --away (затримка 0)--> armed_away
disarmed --home--> armed_home
exit_delay | armed_away | armed_home | entry_delay | alarm --disarm--> disarmed
```

Інші команди дають `409 invalid_transition`. Переходи `entry_delay` і `alarm`
за подіями датчиків з'являться в ЛБ3. Поки діє заглушка: подія `tamper` одразу
переводить об'єкт у `alarm`.

### Пристрій (`device`)

| Метод | Шлях | Призначення |
|---|---|---|
| POST | `/device/events` | Пакет до 200 подій `{channel, event_type, seq, occurred_at, payload}` |
| POST | `/device/heartbeat` | Службове повідомлення; відповідь містить `server_time`, `poll_interval_s`, `facility_mode` |

Повторне надсилання тих самих подій (той самий вузол, датчик, тип і `seq`) не
створює нових записів: відповідь `{"accepted": 0, "duplicates": N, "last_seq": …}`.
Пакет із невідомим каналом відхиляється цілком (`400 unknown_channel`).

Приклад:

```http
POST /api/v1/device/events
X-Device-Token: <token>

{"events": [
  {"channel": 1, "event_type": "opened", "seq": 41, "occurred_at": "2026-10-25T22:04:30Z"},
  {"channel": 3, "event_type": "motion", "seq": 42, "occurred_at": "2026-10-25T22:04:33Z"}
]}
```

### Події та тривоги (`events`)

| Метод | Шлях | Призначення | Право |
|---|---|---|---|
| GET | `/facilities/{id}/events?from=&to=&event_type=&zone_id=` | Архів подій | власник, член родини, гість |
| GET | `/facilities/{id}/alarms?status=&level=` | Тривоги | власник, член родини, гість |
| POST | `/alarms/{alarm_id}/acknowledge` | `acknowledge`, `mark_false`, `resolve` з повторним підтвердженням | власник, член родини |

### Адміністрування (`admin`)

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/admin/users` | Усі користувачі (перегляд фіксується в журналі аудиту) |
| GET | `/admin/audit-log?user_id=&action=&entity_type=` | Журнал аудиту |

Доступ лише для користувача з `is_platform_admin = true`.

## Архітектура серверної частини

```
app/api/v1/*.py     маршрути: розбір запиту, перевірка прав, виклик сервісу
app/services/*.py   бізнес-логіка та робота з моделями (SQL лише тут)
app/models/*.py     моделі SQLAlchemy (таблиці БД)
app/schemas/*.py    схеми Pydantic запитів і відповідей
app/deps.py         залежності: сесія БД, поточний користувач, вузол, пагінація
app/errors.py       єдиний формат помилок; app/i18n.py — переклади
app/security.py     Argon2, JWT, токени пристроїв, TOTP
```
