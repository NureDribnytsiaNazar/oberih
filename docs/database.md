# Схема бази даних «Оберіг»

СУБД: PostgreSQL 16. Моделі описано в `server/app/models/`, міграції — в `server/alembic/`.
Усі часові мітки зберігаються в UTC (`timestamptz`); показ у часовому поясі користувача виконують клієнти.

## ER-діаграма

```mermaid
erDiagram
    TARIFF_PLANS ||--o{ USERS : "обмежує"
    USERS ||--o{ FACILITIES : "володіє"
    USERS ||--o{ FACILITY_MEMBERS : "має роль"
    FACILITIES ||--o{ FACILITY_MEMBERS : "учасники"
    FACILITIES ||--|| FACILITY_SETTINGS : "параметри"
    FACILITIES ||--o{ ZONES : "складається з"
    FACILITIES ||--o{ NODES : "містить"
    FACILITIES ||--o{ SCHEDULES : "розклади"
    FACILITIES ||--o{ EVENTS : "архів"
    FACILITIES ||--o{ ALARMS : "тривоги"
    FACILITIES ||--o{ ARMING_LOG : "журнал охорони"
    FACILITIES ||--o{ TEST_SCENARIOS : "сценарії"
    ZONES ||--o{ SENSORS : "контролюється"
    NODES ||--o{ SENSORS : "підключає"
    NODES ||--o{ EVENTS : "надсилає"
    NODES ||--o{ CERTIFICATES : "автентифікація"
    SENSORS ||--o{ EVENTS : "формує"
    ALARMS ||--o{ ALARM_EVENTS : "складається з"
    EVENTS ||--o{ ALARM_EVENTS : "спричиняє"
    ALARMS ||--o{ ALARM_ACKNOWLEDGEMENTS : "підтвердження"
    ALARMS ||--o{ INCIDENT_SUMMARIES : "хронологія"
    USERS ||--o{ ALARM_ACKNOWLEDGEMENTS : "виконує"
    USERS ||--o{ ARMING_LOG : "ставить і знімає"
    USERS ||--o{ AUDIT_LOG : "дії"
    USERS ||--o{ REFRESH_TOKENS : "сесії"
    USERS ||--o{ PUSH_TOKENS : "пристрої"
    USERS ||--o{ NOTIFICATION_SETTINGS : "сповіщення"
    FACILITIES ||--o{ NOTIFICATION_SETTINGS : "для об'єкта"
    TEST_SCENARIOS ||--o{ SCENARIO_RUNS : "запуски"
    USERS ||--o{ BACKUPS : "створює"

    TARIFF_PLANS {
        uuid id PK
        string code UK
        int max_facilities
        int archive_days
        bool guest_access
        bool false_alarm_stats
        bool incident_timeline
        bool api_access
    }
    USERS {
        uuid id PK
        string email UK
        string password_hash
        string locale
        string timezone
        bool totp_enabled
        bool is_platform_admin
        uuid tariff_plan_id FK
        timestamptz anonymized_at
    }
    FACILITIES {
        uuid id PK
        string name
        uuid owner_id FK
        string mode
        timestamptz mode_changed_at
    }
    FACILITY_SETTINGS {
        uuid facility_id PK
        int exit_delay_s
        int entry_delay_s
        int duplicate_window_s
        int confirm_window_s
        decimal weight_reed
        decimal weight_pir
        decimal weight_tamper
        decimal alarm_threshold
        decimal confirmed_threshold
    }
    FACILITY_MEMBERS {
        uuid id PK
        uuid facility_id FK
        uuid user_id FK
        string role
        timestamptz access_until
    }
    ZONES {
        uuid id PK
        uuid facility_id FK
        string name
        string zone_type
    }
    NODES {
        uuid id PK
        uuid facility_id FK
        string serial UK
        string status
        timestamptz last_seen_at
        bigint last_seq
    }
    SENSORS {
        uuid id PK
        uuid node_id FK
        uuid zone_id FK
        string sensor_type
        smallint channel
    }
    EVENTS {
        bigint id PK
        uuid node_id FK
        uuid sensor_id FK
        string event_type
        bigint seq
        timestamptz occurred_at
        jsonb payload
    }
    ALARMS {
        uuid id PK
        uuid facility_id FK
        string level
        string status
        decimal confidence
        bool is_false
    }
    ALARM_EVENTS {
        uuid alarm_id PK
        bigint event_id PK
    }
    ALARM_ACKNOWLEDGEMENTS {
        uuid id PK
        uuid alarm_id FK
        uuid user_id FK
        string action
        string auth_method
    }
    ARMING_LOG {
        bigint id PK
        uuid facility_id FK
        uuid user_id FK
        string from_mode
        string to_mode
        string source
    }
    INCIDENT_SUMMARIES {
        uuid id PK
        uuid alarm_id FK
        text facts
        text assumptions
    }
    TEST_SCENARIOS {
        uuid id PK
        uuid facility_id FK
        jsonb steps
        jsonb expected
    }
    SCENARIO_RUNS {
        uuid id PK
        uuid scenario_id FK
        bool passed
    }
    AUDIT_LOG {
        bigint id PK
        uuid user_id FK
        string action
        jsonb details
    }
    BACKUPS {
        uuid id PK
        string kind
        string status
        string sha256
    }
    CERTIFICATES {
        uuid id PK
        uuid node_id FK
        string serial_number UK
        string status
    }
    SCHEDULES {
        uuid id PK
        uuid facility_id FK
        string action
        smallint days_mask
        time local_time
    }
    NOTIFICATION_SETTINGS {
        uuid id PK
        uuid user_id FK
        uuid facility_id FK
        string channel
        string min_level
    }
    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash UK
    }
    PUSH_TOKENS {
        uuid id PK
        uuid user_id FK
        string platform
    }
```

## Відповідність вимогам Vision & Scope

| Вимога | Рішення в схемі |
|---|---|
| Режими охорони, зокрема «Вдома» (ФМ-1) | `facilities.mode`: `disarmed`, `exit_delay`, `armed_away`, `armed_home`, `entry_delay`, `alarm` |
| Параметри з розділу 2.2.2 (вікна, ваги, пороги) | `facility_settings`, значення за замовчуванням збігаються з документом |
| Усунення дублікатів (ключ «вузол — датчик — тип — номер») | Унікальне обмеження `uq_events_dedup_key` у `events` |
| Журнал постановки й зняття лише для додавання (ПК-3) | `arming_log`, `alarm_acknowledgements`, `audit_log`; заборона зміни й видалення — тригерами в міграції |
| Індекс достовірності й тривоги | `alarms.confidence`, `alarms.level`; зв'язок із подіями через `alarm_events` |
| Статистика хибних спрацювань (FAR) | `alarms.is_false` та `alarm_events` → `events.sensor_id`; обчислюється запитом |
| Ролі й гостьовий доступ у часових межах | `facility_members.role`, `access_from`, `access_until` |
| Тарифні плани з обмеженнями (ВО-8) | `tariff_plans`, початкові дані додаються міграцією |
| Хронологія інциденту (факти й припущення окремо) | `incident_summaries.facts` і `.assumptions` |
| Відтворення тестових сценаріїв | `test_scenarios`, `scenario_runs` |
| Адміністрування: резервні копії, сертифікати | `backups`, `certificates` |
| Захист даних (GDPR): видалення й експорт | `users.anonymized_at`, `users.privacy_consent_at`, `audit_log` |
| Інтернаціоналізація | `users.locale`, `users.timezone`, `users.measurement_system`; час у UTC |
| Недоступність вузла | `nodes.status`, `nodes.last_seen_at`, події `node_offline` та `node_online` |
