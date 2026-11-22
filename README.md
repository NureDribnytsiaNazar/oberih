# Оберіг

**Програмна система для безпеки житла** (Home Security Software System).

Система складається із серверної частини (Python, FastAPI, PostgreSQL) та IoT-вузла на мікроконтролері ESP32 (C++). Охорона житла ґрунтується на зонах, режимах охорони, датчиках відкривання й руху та підтвердженні дій уповноваженими користувачами.

## Структура репозиторію

| Каталог | Призначення |
|---|---|
| `server/` | Серверна частина: REST API, бізнес-логіка, адміністрування |
| `server/app/` | Код застосунку: маршрути, сервіси, моделі, схеми |
| `server/alembic/` | Міграції бази даних |
| `server/scripts/` | Початкові дані, секрети вузла (`provision_node`), експорт OpenAPI, діаграма БД |
| `server/tests/` | Автоматичні тести (pytest) |
| `iot/` | Програма IoT-вузла на ESP32 (C++, PlatformIO, симуляція Wokwi) |
| `iot/src/` | Модулі вузла: фільтри, автомат режимів, буфер, повтори, команди, налаштування |
| `iot/test/` | Юніт-тести чистої логіки вузла (Unity, `pio test -e native`) |
| `docs/` | Специфікація API, схема БД, діаграми, прийняті рішення |
| `docker-compose.yml` | Середовище розробки (лише PostgreSQL 16) |
| `docker-compose.prod.yml` | Розгортання: PostgreSQL, застосунок, Nginx (ЛБ5) |
| `deploy/` | Конфігурація Nginx, скрипти секретів, сертифіката, smoke-тесту й копій БД |

## Швидкий старт (Windows, PowerShell)

Потрібні Docker Desktop та Python 3.13.

```powershell
# 1. Налаштування середовища: скопіюйте приклад і впишіть JWT_SECRET
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # значення для JWT_SECRET

# 2. База даних
docker compose up -d db

# 3. Серверна частина
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # застосунок + інструменти перевірки
alembic upgrade head

# 4. Центр сертифікації для сертифікатів вузлів (один раз; каталог CA_DIR)
python -m scripts.init_ca

# 5. Демо-дані (необов'язково): користувачі всіх ролей, об'єкт під охороною,
#    вузол, датчики, закриті тривоги, сценарій, сертифікати
$env:SEED_PASSWORD = "оберіть-пароль"     # інакше пароль згенерується й виведеться
python -m scripts.seed

# 6. Запуск (разом із фоновим виконавцем таймерів)
uvicorn app.main:app --reload
```

## Змінні середовища

| Змінна | За замовчуванням | Призначення |
|---|---|---|
| `DATABASE_URL` | — (обов'язкова) | Рядок підключення до PostgreSQL |
| `JWT_SECRET` | — (обов'язкова, ≥ 32 символи) | Секрет підпису токенів доступу |
| `WORKER_ENABLED` | `true` | Фоновий виконавець таймерів (`false` — вимкнено, як у тестах) |
| `WORKER_INTERVAL_S` | `5` | Як часто перевіряти затримки, недоступні вузли й сертифікати, с |
| `PURGE_INTERVAL_H` | `24` | Як часто видаляти дані, старші за строк зберігання тарифу, год |
| `BACKUP_DIR` | `backups` | Каталог файлів резервних копій (у `.gitignore`) |
| `CA_DIR` | `ca` | Каталог ключа й сертифіката центру сертифікації (у `.gitignore`) |
| `SUMMARY_PROVIDER` | `template` | Хронологія інциденту: `template` або `external` (заглушка) |
| `LLM_API_URL`, `LLM_MODEL` | — | Налаштування зовнішньої мовної моделі (у ЛБ3 не викликається) |
| `SEED_PASSWORD` | — | Пароль демо-користувачів для `scripts.seed` |

Шляхи `BACKUP_DIR` і `CA_DIR` відносні до каталогу, з якого запущено сервер
(`server/`). Ключ центру сертифікації та файли копій не додавайте до
репозиторію.

Після запуску:

- документація API (Swagger UI): <http://localhost:8000/docs>;
- перевірка стану: <http://localhost:8000/api/v1/health>.

## IoT-вузол (ESP32, Wokwi)

Прошивка в `iot/` (PlatformIO, плата `esp32dev`, фреймворк Arduino). Логіку
(фільтр брязкоту, блокування PIR, автомат режимів, буфер подій, повтори,
перевірку команд, налаштування, формат JSON) написано без Arduino API, тому
її юніт-тести виконуються на ПК.

Потрібно: [PlatformIO Core](https://platformio.org/install/cli) (`pio`),
для тестів на ПК — компілятор GCC (MinGW-w64, наприклад
`winget install BrechtSanders.WinLibs.POSIX.UCRT`), для симуляції —
розширення **Wokwi for VS Code** з ліцензією (F1 → *Wokwi: Request a new
License*).

```powershell
# 1. Сервер із TLS за TCP-тунелем bore (Wokwi бачить лише публічні адреси;
#    докладно — docs/lab4-demo.md, розділ 0, і припущення 50б).
cd server
python -m scripts.make_dev_cert --names bore.pub localhost
uvicorn app.main:app --port 8443 --ssl-keyfile certs\server.key --ssl-certfile certs\server.crt --timeout-keep-alive 120
#    в іншому вікні: bore local 8443 --to bore.pub  -> bore.pub:<порт>
# 2. Секрети вузла: новий токен і ключ підпису команд, адреса й сертифікат
#    сервера -> iot/include/secrets.h (не комітиться).
python -m scripts.provision_node --server-url https://bore.pub:<порт> --ca-file certs\server.crt
cd ..\iot

# 3. Юніт-тести логіки на ПК
pio test -e native

# 4. Збирання прошивки для симуляції
pio run -e esp32dev
```

Далі у VS Code відкрийте `iot/diagram.json` і запустіть F1 → *Wokwi: Start
Simulator*. Перемикачі `1 Door`, `2 Window`, `4 Tamper` — контакти дверей,
вікна й корпусу, датчик `3 PIR` — рух. RGB-світлодіод показує режим
(зелений — знято, жовтий — «Вдома», червоний — охорона, мигання — затримки й
тривога, синій спалах — немає зв'язку), зумер — тривогу й втрату зв'язку.

Налаштування вузла (ІК-8) змінюються в консолі Serial Monitor (BLE у Wokwi не
емулюється, ЗЛ-1): `help`, `get`, `set exit_delay 20`, `set debounce_ms 80`,
`save`, `defaults`, `status`, `buffer`, `net off|on` (імітація втрати
зв'язку), `sim bounce 1` (серія перемикань для фільтра брязкоту),
`sim badcmd` (команда з підробленим підписом). Сервер змінює налаштування
вузла через `PATCH /facilities/{id}/nodes/{node_id}` і налаштування об'єкта.

Без сертифіката-якоря (`--no-ca`) прошивку для розробки збирають у
середовищі `esp32dev_devtls` (TLS без перевірки сертифіката) і змінюють
шляхи в `iot/wokwi.toml`.

## Розгортання (Docker Compose + Nginx)

```powershell
.\deploy\init-env.ps1        # .env.prod із випадковими секретами
.\deploy\make-dev-cert.ps1   # самопідписаний сертифікат для Nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -e SEED_PASSWORD=Demo-Password-1 api python -m scripts.seed
.\deploy\smoke-test.ps1 -BaseUrl https://localhost -Password Demo-Password-1 -SkipCertificateCheck
cloudflared tunnel --url http://localhost:8081   # публічна HTTPS-адреса для вузла у Wokwi
```

Подробиці (варіанти локально/VPS, ліміти Nginx, резервне копіювання,
секрети вузла в розгортанні) — у [`docs/deploy.md`](docs/deploy.md).

## Тести та якість коду

Тести створюють окрему БД `oberih_test` у тому самому контейнері PostgreSQL і
застосовують до неї міграції (зокрема, перевіряють їх відкат).

```powershell
cd server
pytest                 # автоматичні тести
black --check .        # форматування
flake8                 # стиль (PEP 8)
mypy app scripts tests # перевірка типів
```

Фоновий виконавець у тестах вимкнено (`WORKER_ENABLED=false`): таймери
перевіряються викликом `process_timers(db, now)` із віртуальним часом.

## Документація

| Документ | Зміст |
|---|---|
| [`docs/api.md`](docs/api.md) | Опис REST API, права доступу, формат помилок |
| [`docs/openapi.json`](docs/openapi.json) | Специфікація OpenAPI (`python -m scripts.export_openapi`) |
| [`docs/database.md`](docs/database.md) | ER-діаграма, міграції, індекси, відповідність вимогам |
| [`docs/diagrams/`](docs/diagrams/) | Прецеденти (сервер, IoT-вузол), структура БД, діяльність (конвеєр подій, резервні копії, цикл вузла), взаємодія (подія -> тривога, таймери, команда вузлу) |
| [`docs/lab3-demo.md`](docs/lab3-demo.md) | Покрокова демонстрація бізнес-логіки й адміністрування (PowerShell) |
| [`docs/deploy.md`](docs/deploy.md) | Розгортання: Docker, Compose, Nginx, тунель або VPS, smoke-тест, копії БД |
| [`docs/lab5-demo.md`](docs/lab5-demo.md) | Наскрізна демонстрація на розгорнутій системі (вузол у Wokwi + сервер) |
| [`docs/lab4-demo.md`](docs/lab4-demo.md) | Демонстрація IoT-вузла у Wokwi: бізнес-логіка, налаштування, взаємодія із сервером |
| [`docs/assumptions.md`](docs/assumptions.md) | Рішення, прийняті там, де вимоги неоднозначні |

## Автор

Дрібниця Назар Сергійович, ПЗПІ-24-6, ХНУРЕ.
