# Оберіг

**Програмна система для безпеки житла** (Home Security Software System).

Система складається із серверної частини (Python, FastAPI, PostgreSQL) та IoT-вузла на мікроконтролері ESP32 (C++). Охорона житла ґрунтується на зонах, режимах охорони, датчиках відкривання й руху та підтвердженні дій уповноваженими користувачами.

## Структура репозиторію

| Каталог | Призначення |
|---|---|
| `server/` | Серверна частина: REST API, бізнес-логіка, адміністрування |
| `server/app/` | Код застосунку: маршрути, сервіси, моделі, схеми |
| `server/alembic/` | Міграції бази даних |
| `server/scripts/` | Початкові дані, експорт OpenAPI, генерація діаграми БД |
| `server/tests/` | Автоматичні тести (pytest) |
| `iot/` | Програма IoT-вузла на ESP32 (C++, PlatformIO, симуляція Wokwi) |
| `docs/` | Специфікація API, схема БД, діаграми, прийняті рішення |
| `docker-compose.yml` | Локальне середовище (PostgreSQL 16) |

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
pip install -r requirements.txt
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
| [`docs/diagrams/`](docs/diagrams/) | Прецеденти, структура БД, діяльність (конвеєр подій, резервні копії), взаємодія (подія -> тривога, таймери) |
| [`docs/lab3-demo.md`](docs/lab3-demo.md) | Покрокова демонстрація бізнес-логіки й адміністрування (PowerShell) |
| [`docs/assumptions.md`](docs/assumptions.md) | Рішення, прийняті там, де вимоги неоднозначні |

## Автор

Дрібниця Назар Сергійович, ПЗПІ-24-6, ХНУРЕ.
