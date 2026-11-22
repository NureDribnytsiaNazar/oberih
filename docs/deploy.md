# Розгортання «Оберіг» (ЛБ5)

Система запускається однією командою Docker Compose: PostgreSQL 16,
застосунок (FastAPI + фоновий виконавець таймерів) і Nginx (TLS, зворотний
проксі, обмеження частоти запитів). IoT-вузол у Wokwi підключається до
публічної HTTPS-адреси.

```
 Wokwi (ESP32) --TLS усередині TCP--> bore.pub:<порт> --TCP--> :443 ┐
 Браузер, PowerShell ------------------------HTTPS--> :443 (HTTP :80 -> 301) ─┤
 (необов'язково) тунель, що сам завершує TLS --HTTP--> 127.0.0.1:8081 ─┤
                                                                nginx │
                               api:8000 (uvicorn, лише мережа compose) <┘
                                                    │
                                      db:5432 (лише мережа compose)
```

## Склад

| Файл | Призначення |
|---|---|
| `server/Dockerfile` | Багатоетапний образ: Python 3.13 slim, віртуальне середовище, користувач `oberih` без привілеїв, `HEALTHCHECK` на `/api/v1/health` (перевіряє й БД) |
| `docker-compose.prod.yml` | Сервіси `db`, `migrate` (одноразово: `alembic upgrade head` і центр сертифікації), `api`, `nginx`; томи `db-data` і `app-data` (`/data/backups`, `/data/ca`) |
| `.env.prod.example` | Параметри без секретів; `.env.prod` створює `deploy/init-env.ps1` |
| `deploy/nginx/oberih.conf` | Сервери Nginx: HTTP -> HTTPS, HTTPS, вхід тунелю; зони `limit_req` |
| `deploy/nginx/locations.conf` | Спільні маршрути, заголовки безпеки, ліміт тіла, `X-Forwarded-*` |
| `deploy/make-dev-cert.ps1`, `.sh` | Самопідписаний сертифікат для локального запуску |
| `deploy/smoke-test.ps1` | Перевірка розгорнутої системи (код виходу 1 при збої) |
| `deploy/backup-db.ps1` | `pg_dump` тому БД, перевірка й відновлення |

Порядок запуску забезпечує `depends_on`: `db` (healthy) -> `migrate`
(completed successfully) -> `api` (healthy) -> `nginx`. Назовні публікуються
лише порти Nginx: `HTTP_PORT` (80), `HTTPS_PORT` (443) і `TUNNEL_PORT`
(8081, лише на `127.0.0.1`).

## Варіант A: локально (Docker Desktop) + тунель — за замовчуванням

```powershell
cd D:\ARK\oberih
.\deploy\init-env.ps1                  # .env.prod з випадковими паролем БД і JWT_SECRET
.\deploy\make-dev-cert.ps1             # deploy/certs/server.crt, server.key
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# Демо-дані (пароль демо-користувачів задаєте самі)
docker compose -f docker-compose.prod.yml --env-file .env.prod exec `
    -e SEED_PASSWORD=Demo-Password-1 api python -m scripts.seed

# Перевірка
.\deploy\smoke-test.ps1 -BaseUrl https://localhost -Password Demo-Password-1 -SkipCertificateCheck
```

Якщо порти 80/443 зайняті: `.\deploy\init-env.ps1 -HttpPort 8080 -HttpsPort 8443`.

Публічна адреса для вузла — TCP-тунель **bore** (`bore.exe` з
[github.com/ekzhang/bore/releases](https://github.com/ekzhang/bore/releases),
архів `x86_64-pc-windows-msvc`). Тунель лише пересилає байти, TLS
завершує наш Nginx (таймаут рукопожаття 60 с). Тунелі, що самі завершують
TLS (Cloudflare Quick Tunnel), для вузла у Wokwi не годяться: вони рвуть
рукопожаття через ~10 с, а ESP32 у симуляторі рахує його ~11 с (припущення
50б). Сертифікат Nginx має містити ім'я `bore.pub` (`make-dev-cert.ps1` додає
його за замовчуванням).

```powershell
& "$env:LOCALAPPDATA\Programs\bore\bore.exe" local 443 --to bore.pub   # або HTTPS_PORT
```

Команда виводить `listening at bore.pub:<порт>`. Порт змінюється з кожним
запуском; `bore.pub` — публічний сервер-хобі без гарантій доступності.

Секрети вузла для цієї адреси (токен, ключ команд і сертифікат Nginx, якому
довірятиме вузол). У розгортанні БД назовні не відкрита, тому скрипт
виконується всередині контейнера `api`:

```powershell
$C = "-f", "docker-compose.prod.yml", "--env-file", ".env.prod"
docker compose @C cp deploy/certs/server.crt api:/data/nginx.crt
docker compose @C exec api python -m scripts.provision_node `
    --server-url https://bore.pub:<порт> --ca-file /data/nginx.crt --output /data/secrets.h
docker compose @C cp api:/data/secrets.h iot/include/secrets.h
docker compose @C exec api rm /data/secrets.h /data/nginx.crt
cd iot; pio run -e esp32dev
```

Вхід `127.0.0.1:8081` (HTTP без редиректу) лишається для тунелів, що самі
завершують TLS, наприклад `cloudflared tunnel --url http://localhost:8081`
для доступу браузером; вузлу він не потрібен.

## Варіант B: VPS або хмарна ВМ

Той самий репозиторій і той самий compose; змінюються лише `.env.prod` і
сертифікат:

1. Встановити Docker Engine із плагіном Compose, клонувати репозиторій,
   виконати `deploy/init-env.ps1` (PowerShell 7 на Linux) або заповнити
   `.env.prod` вручну за `.env.prod.example`.
2. Отримати сертифікат Let's Encrypt для домену (наприклад,
   `certbot certonly --standalone -d oberih.example.com` до запуску Nginx) і
   скопіювати `fullchain.pem` -> `deploy/certs/server.crt`,
   `privkey.pem` -> `deploy/certs/server.key`.
3. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
4. Порт 8081 на VPS не потрібен (тунелю немає), його публікацію на
   `127.0.0.1` можна залишити.
5. Секрети вузла: `provision_node --server-url https://oberih.example.com`
   (якір — видавець сертифіката Let's Encrypt; для справжньої плати можна
   `--ca-level root`, тоді це ISRG Root X1; скрипт визначить його сам).

## Nginx

- **TLS:** TLS 1.2–1.3; `HTTP_PORT` -> 301 на `https://<host>:<HTTPS_PORT>`
  (порт підставляється шаблоном образу nginx).
- **Заголовки безпеки:** `Strict-Transport-Security`, `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Content-Security-Policy: frame-ancestors 'none'`; `server_tokens off`.
- **Ліміт тіла:** 2 МБ.
- **Обмеження частоти (СЧ-1)**, відповідь `429`:

  | Маршрут | Ключ | Швидкість | Сплеск |
  |---|---|---|---|
  | `/api/v1/auth/*` | адреса клієнта | 10 за хвилину | 5 |
  | `/api/v1/device/*` | токен пристрою | 2 за секунду | 20 |
  | `/api/v1/device/*` | адреса клієнта | 10 за секунду | 40 |
  | решта API | адреса клієнта | 10 за секунду | 20 |

  Вузол надсилає heartbeat раз на 30 с і пакети до 20 подій, тому навіть
  буфер після відновлення зв'язку вкладається в ліміт (smoke-тест надсилає 10
  запитів вузла поспіль без `429`). На `429` вузол відповідає повтором зі
  зростаючою затримкою, події не втрачаються.
- **Адреса клієнта:** на портах 80/443 — адреса з'єднання (заголовку
  `X-Forwarded-For` не довіряємо, інакше його підробка обходить ліміт
  входу, припущення 53); `real_ip_header X-Forwarded-For` діє лише на вході
  тунелю `127.0.0.1:8081`. Застосунку передається один `X-Forwarded-For` із
  визначеною адресою (його бачить журнал охорони).
- **Зміна конфігурації Nginx:** шаблон читається під час старту контейнера,
  тож після правки `deploy/nginx/*.conf` потрібен
  `docker compose -f docker-compose.prod.yml --env-file .env.prod restart nginx`
  (`up -d` контейнер без змін у compose не перезапускає).

## Продуктивна конфігурація

| Параметр | Значення в розгортанні |
|---|---|
| `JWT_SECRET` | випадковий, 64 символи (застосунок не стартує з коротшим за 32) |
| `POSTGRES_PASSWORD` | випадковий; БД не публікується назовні |
| `WORKER_ENABLED` | `true` в `api`, `false` в `migrate` |
| `BACKUP_DIR`, `CA_DIR` | `/data/backups`, `/data/ca` у томі `app-data` (переживають перезапуск; `init_ca` не перезаписує наявний центр) |
| Журнали | uvicorn без заголовка `Server`; паролі й токени не журналюються (помилки валідації — без значень полів) |
| CORS | не вмикається: веб-клієнта в цій роботі немає |

**Масштабування (СЧ-12).** Фоновий виконавець працює в процесі `api`,
розгортання має один екземпляр. Прохід таймерів захищено
`pg_try_advisory_xact_lock`, тому за кількох екземплярів таймери виконає
лише один (тест `test_timer_pass_skipped_when_another_instance_holds_lock`).
Очищення застарілих даних може виконатися паралельно, але воно ідемпотентне.

## Резервне копіювання

- **Логічні копії застосунку** (`POST /admin/backups`, ЛБ3) лежать у томі
  `app-data` (`/data/backups`); відновлення — `POST /admin/backups/{id}/restore`.
- **Копія тому БД:**

  ```powershell
  .\deploy\backup-db.ps1 backup     # deploy/backups/oberih-<час>.dump (pg_dump -Fc)
  .\deploy\backup-db.ps1 verify     # відновлення у тимчасову БД і порівняння кількості рядків
  .\deploy\backup-db.ps1 restore    # у робочу БД (спершу зупиніть api)
  ```

## Взаємна TLS-автентифікація вузла (mTLS)

Не реалізовано (припущення 30 і 55). У варіанті A TLS завершується в мережі
Cloudflare, тож клієнтський сертифікат вузла до Nginx не доходить. Вузол
автентифікується токеном пристрою, а команди перевіряє підписом HMAC.
Сертифікати вузлів (ЛБ3) і далі блокують вузол із відкликаним сертифікатом.
Для варіанта B розвиток такий: `ssl_client_certificate` (корінь центру
сертифікації з `CA_DIR`), `ssl_verify_client optional`, заголовок
`X-Client-Cert-Serial $ssl_client_serial`, який Nginx завжди перезаписує, і
звірка серійного номера з таблицею `certificates`.

## Перевірка з чистого клону (виконано)

```powershell
git clone -b lab5 https://github.com/NureDribnytsiaNazar/oberih.git; cd oberih
.\deploy\init-env.ps1 -HttpPort 8080 -HttpsPort 8443
.\deploy\make-dev-cert.ps1
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -e SEED_PASSWORD=Demo-Password-1 api python -m scripts.seed
.\deploy\smoke-test.ps1 -BaseUrl https://localhost:8443 -Password Demo-Password-1 -SkipCertificateCheck   # 14/14
.\deploy\smoke-test.ps1 -BaseUrl http://localhost:8081 -Password Demo-Password-1 -SkipRateLimitCheck     # вхід тунелю
.\deploy\backup-db.ps1 backup; .\deploy\backup-db.ps1 verify
```

Зупинка зі збереженням даних: `docker compose -f docker-compose.prod.yml
--env-file .env.prod down`. Повне видалення разом із томами: `down -v`.
