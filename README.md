# Оберіг

**Програмна система для безпеки житла** (Home Security Software System).

Система складається із серверної частини (Python, FastAPI, PostgreSQL) та IoT-вузла на мікроконтролері ESP32 (C++). Охорона житла ґрунтується на зонах, режимах охорони, датчиках відкривання й руху та підтвердженні дій уповноваженими користувачами.

## Структура репозиторію

| Каталог | Призначення |
|---|---|
| `server/` | Серверна частина: REST API, бізнес-логіка, адміністрування |
| `iot/` | Програма IoT-вузла на ESP32 (C++, PlatformIO, симуляція Wokwi) |
| `docs/` | Діаграми та специфікація API |
| `docker-compose.yml` | Локальне середовище (PostgreSQL) |

## Швидкий старт

Потрібні Docker Desktop та Python 3.13.

```powershell
# 1. Налаштування середовища
Copy-Item .env.example .env

# 2. База даних
docker compose up -d db

# 3. Серверна частина
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Після запуску документація API доступна за адресою <http://localhost:8000/docs>, перевірка стану сервісу — <http://localhost:8000/health>.

## Автор

Дрібниця Назар Сергійович, ПЗПІ-24-6, ХНУРЕ.
