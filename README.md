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

# 4. Демо-дані (необов'язково): користувачі всіх ролей, об'єкт, вузол, датчики
$env:SEED_PASSWORD = "оберіть-пароль"     # інакше пароль згенерується й виведеться
python -m scripts.seed

# 5. Запуск
uvicorn app.main:app --reload
```

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

## Документація

| Документ | Зміст |
|---|---|
| [`docs/api.md`](docs/api.md) | Опис REST API, права доступу, формат помилок |
| [`docs/openapi.json`](docs/openapi.json) | Специфікація OpenAPI (`python -m scripts.export_openapi`) |
| [`docs/database.md`](docs/database.md) | ER-діаграма, міграції, індекси, відповідність вимогам |
| [`docs/diagrams/`](docs/diagrams/) | Діаграма прецедентів і структура БД (PlantUML, PNG) |
| [`docs/assumptions.md`](docs/assumptions.md) | Рішення, прийняті там, де вимоги неоднозначні |

## Автор

Дрібниця Назар Сергійович, ПЗПІ-24-6, ХНУРЕ.
