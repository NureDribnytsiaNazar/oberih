"""Локалізація повідомлень API (українська та англійська, ФМ-10)."""

from app.models.enums import Locale

DEFAULT_LOCALE = Locale.UK

# Код помилки -> повідомлення кожною мовою.
MESSAGES: dict[str, dict[Locale, str]] = {
    "validation_error": {
        Locale.UK: "Некоректні дані запиту",
        Locale.EN: "Invalid request data",
    },
    "not_found": {
        Locale.UK: "Ресурс не знайдено",
        Locale.EN: "Resource not found",
    },
    "method_not_allowed": {
        Locale.UK: "Метод не підтримується",
        Locale.EN: "Method not allowed",
    },
    "internal_error": {
        Locale.UK: "Внутрішня помилка сервера",
        Locale.EN: "Internal server error",
    },
    "not_authenticated": {
        Locale.UK: "Потрібна автентифікація",
        Locale.EN: "Authentication required",
    },
    "invalid_credentials": {
        Locale.UK: "Неправильна електронна пошта або пароль",
        Locale.EN: "Invalid email or password",
    },
    "invalid_token": {
        Locale.UK: "Токен недійсний або прострочений",
        Locale.EN: "Token is invalid or expired",
    },
    "totp_required": {
        Locale.UK: "Потрібен одноразовий код двофакторної автентифікації",
        Locale.EN: "A two-factor authentication code is required",
    },
    "totp_invalid": {
        Locale.UK: "Неправильний одноразовий код",
        Locale.EN: "Invalid one-time code",
    },
    "totp_not_initialized": {
        Locale.UK: "Спочатку увімкніть двофакторну автентифікацію",
        Locale.EN: "Enable two-factor authentication first",
    },
    "email_taken": {
        Locale.UK: "Користувач із такою електронною поштою вже існує",
        Locale.EN: "A user with this email already exists",
    },
    "consent_required": {
        Locale.UK: "Потрібна згода на обробку персональних даних",
        Locale.EN: "Consent to personal data processing is required",
    },
    "owns_facilities": {
        Locale.UK: "Спочатку видаліть або передайте свої об'єкти",
        Locale.EN: "Delete or transfer your facilities first",
    },
    "forbidden": {
        Locale.UK: "Недостатньо прав для цієї дії",
        Locale.EN: "You are not allowed to perform this action",
    },
    "access_expired": {
        Locale.UK: "Термін гостьового доступу не настав або минув",
        Locale.EN: "Guest access is not active at this time",
    },
    "reauth_required": {
        Locale.UK: "Підтвердьте дію паролем або одноразовим кодом",
        Locale.EN: "Confirm this action with your password or one-time code",
    },
    "reauth_failed": {
        Locale.UK: "Повторне підтвердження не пройдено",
        Locale.EN: "Re-authentication failed",
    },
    "tariff_limit": {
        Locale.UK: "Досягнуто ліміту об'єктів для вашого тарифного плану",
        Locale.EN: "Your tariff plan facility limit has been reached",
    },
    "tariff_feature": {
        Locale.UK: "Функція недоступна у вашому тарифному плані",
        Locale.EN: "This feature is not available in your tariff plan",
    },
    "invalid_transition": {
        Locale.UK: "Перехід у цей режим охорони зараз неможливий",
        Locale.EN: "This arming mode change is not allowed now",
    },
    "conflict": {
        Locale.UK: "Запис із такими даними вже існує",
        Locale.EN: "A record with the same data already exists",
    },
    "in_use": {
        Locale.UK: "Ресурс використовується і не може бути видалений",
        Locale.EN: "The resource is in use and cannot be deleted",
    },
    "member_exists": {
        Locale.UK: "Користувач уже є учасником об'єкта",
        Locale.EN: "The user is already a member of this facility",
    },
    "user_not_found": {
        Locale.UK: "Користувача з такою електронною поштою не знайдено",
        Locale.EN: "No user with this email was found",
    },
    "owner_immutable": {
        Locale.UK: "Роль власника об'єкта не можна змінити чи видалити",
        Locale.EN: "The facility owner role cannot be changed or removed",
    },
    "guest_period_required": {
        Locale.UK: "Для гостя потрібно вказати кінець терміну доступу",
        Locale.EN: "An access end time is required for a guest",
    },
    "invalid_period": {
        Locale.UK: "Початок періоду має бути раніше за його кінець",
        Locale.EN: "The period start must be before its end",
    },
    "invalid_timezone": {
        Locale.UK: "Невідомий часовий пояс",
        Locale.EN: "Unknown time zone",
    },
    "invalid_thresholds": {
        Locale.UK: "Поріг тривоги не може перевищувати поріг підтвердженої тривоги",
        Locale.EN: "The alarm threshold cannot exceed the confirmed threshold",
    },
    "zone_mismatch": {
        Locale.UK: "Зона належить іншому об'єкту",
        Locale.EN: "The zone belongs to another facility",
    },
    "unknown_channel": {
        Locale.UK: "На вузлі немає датчика з таким каналом",
        Locale.EN: "The node has no sensor on this channel",
    },
    "device_unauthorized": {
        Locale.UK: "Пристрій не автентифіковано",
        Locale.EN: "Device is not authenticated",
    },
    "account_blocked": {
        Locale.UK: "Обліковий запис заблоковано адміністратором",
        Locale.EN: "The account has been blocked by an administrator",
    },
    "cannot_block_self": {
        Locale.UK: "Не можна заблокувати власний обліковий запис",
        Locale.EN: "You cannot block your own account",
    },
    "last_admin": {
        Locale.UK: "Не можна зняти права в останнього адміністратора",
        Locale.EN: "The last administrator cannot lose administrator rights",
    },
    "user_anonymized": {
        Locale.UK: "Обліковий запис знеособлено, його не можна змінити",
        Locale.EN: "The account has been anonymized and cannot be changed",
    },
    "unknown_tariff": {
        Locale.UK: "Невідомий тарифний план",
        Locale.EN: "Unknown tariff plan",
    },
    "backup_failed": {
        Locale.UK: "Не вдалося записати файл резервної копії",
        Locale.EN: "The backup file could not be written",
    },
    "backup_not_ready": {
        Locale.UK: "Резервна копія не завершена",
        Locale.EN: "The backup is not completed",
    },
    "backup_file_missing": {
        Locale.UK: "Файл резервної копії не знайдено",
        Locale.EN: "The backup file was not found",
    },
    "backup_corrupted": {
        Locale.UK: "Файл резервної копії пошкоджено (контрольна сума не збігається)",
        Locale.EN: "The backup file is corrupted (checksum mismatch)",
    },
    "backup_unsupported_format": {
        Locale.UK: "Непідтримувана версія формату резервної копії",
        Locale.EN: "Unsupported backup format version",
    },
    "backup_restore_failed": {
        Locale.UK: "Відновлення не вдалося, жодних змін не внесено",
        Locale.EN: "Restore failed; no changes were made",
    },
    "certificate_invalid": {
        Locale.UK: "Сертифікат пристрою відкликано або строк його дії минув",
        Locale.EN: "The device certificate is revoked or expired",
    },
    "certificate_not_active": {
        Locale.UK: "Сертифікат уже не є чинним",
        Locale.EN: "The certificate is no longer active",
    },
    "ca_not_initialized": {
        Locale.UK: "Центр сертифікації не ініціалізовано (scripts/init_ca.py)",
        Locale.EN: "The certificate authority is not initialized (scripts/init_ca.py)",
    },
    "import_invalid": {
        Locale.UK: "Документ імпорту містить помилку (див. details)",
        Locale.EN: "The import document contains an error (see details)",
    },
    "csv.id": {Locale.UK: "Номер", Locale.EN: "Number"},
    "csv.time_utc": {Locale.UK: "Час (UTC)", Locale.EN: "Time (UTC)"},
    "csv.time_local": {Locale.UK: "Місцевий час", Locale.EN: "Local time"},
    "csv.event": {Locale.UK: "Подія", Locale.EN: "Event"},
    "csv.zone": {Locale.UK: "Зона", Locale.EN: "Zone"},
    "csv.sensor": {Locale.UK: "Датчик", Locale.EN: "Sensor"},
    "csv.seq": {Locale.UK: "Порядковий номер", Locale.EN: "Sequence"},
    "event.opened": {Locale.UK: "Відчинено", Locale.EN: "Opened"},
    "event.closed": {Locale.UK: "Зачинено", Locale.EN: "Closed"},
    "event.motion": {Locale.UK: "Рух", Locale.EN: "Motion"},
    "event.tamper": {Locale.UK: "Втручання в корпус", Locale.EN: "Tamper"},
    "event.tamper_restored": {
        Locale.UK: "Корпус закрито",
        Locale.EN: "Tamper restored",
    },
    "event.node_offline": {Locale.UK: "Вузол недоступний", Locale.EN: "Node offline"},
    "event.node_online": {Locale.UK: "Вузол на зв'язку", Locale.EN: "Node online"},
    "incident.fact": {
        Locale.UK: "[подія №{number}] {time} UTC — зона «{zone}»: {event}",
        Locale.EN: '[event #{number}] {time} UTC — zone "{zone}": {event}',
    },
    "incident.assume_tamper": {
        Locale.UK: "Можлива спроба саботажу: відкрито або знято корпус вузла.",
        Locale.EN: "Possible sabotage attempt: the node case was opened or removed.",
    },
    "incident.assume_intrusion": {
        Locale.UK: "Імовірне проникнення: відчинення на периметрі з подальшим "
        "рухом усередині приміщення.",
        Locale.EN: "Likely intrusion: a perimeter opening followed by motion "
        "inside the premises.",
    },
    "incident.assume_door_only": {
        Locale.UK: "Відчинення без підтвердження рухом: можливе хибне "
        "спрацювання або охорону не знято вчасно.",
        Locale.EN: "Opening without confirming motion: possibly a false alarm "
        "or the system was not disarmed in time.",
    },
    "incident.assume_motion_only": {
        Locale.UK: "Рух без відчинення периметра: можливе хибне спрацювання "
        "датчика руху або особа вже була всередині.",
        Locale.EN: "Motion without a perimeter opening: possibly a false motion "
        "detection or someone was already inside.",
    },
    "service_unavailable": {
        Locale.UK: "Сервіс тимчасово недоступний (немає зв'язку з БД)",
        Locale.EN: "Service temporarily unavailable (database is unreachable)",
    },
    "llm_unavailable": {
        Locale.UK: "Зовнішня мовна модель недоступна",
        Locale.EN: "The external language model is unavailable",
    },
    "far.check_sensor": {
        Locale.UK: "Частка хибних спрацювань висока: перевірте розташування "
        "або чутливість датчика",
        Locale.EN: "The false alarm rate is high: check the sensor placement "
        "or sensitivity",
    },
    "scenario_sensor_missing": {
        Locale.UK: "Сценарій посилається на датчик, якого немає на об'єкті",
        Locale.EN: "The scenario refers to a sensor that is not in the facility",
    },
    "alarm_closed": {
        Locale.UK: "Тривогу вже закрито",
        Locale.EN: "The alarm is already closed",
    },
}


def match_accept_language(header: str | None) -> Locale | None:
    """Мова з заголовка Accept-Language з урахуванням пріоритетів q або None."""
    if not header:
        return None
    candidates: list[tuple[float, str]] = []
    for part in header.split(","):
        pieces = part.strip().split(";")
        tag = pieces[0].strip().lower()
        weight = 1.0
        for param in pieces[1:]:
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    weight = float(value)
                except ValueError:
                    weight = 0.0
        candidates.append((weight, tag))
    # Стабільне сортування зберігає порядок для однакових пріоритетів.
    for _, tag in sorted(candidates, key=lambda item: -item[0]):
        language = tag.split("-")[0]
        for locale in Locale:
            if locale.value == language:
                return locale
    return None


def parse_accept_language(header: str | None) -> Locale:
    """Мова із заголовка Accept-Language або мова за замовчуванням."""
    return match_accept_language(header) or DEFAULT_LOCALE


def resolve_locale(header: str | None, profile_locale: Locale | None) -> Locale:
    """Мова відповіді: явний заголовок, потім профіль користувача, потім uk."""
    return match_accept_language(header) or profile_locale or DEFAULT_LOCALE


def translate(code: str, locale: Locale) -> str:
    """Повертає текст для коду потрібною мовою.

    У робочому режимі невідомий код не ламає відповідь (повертається
    загальне повідомлення); повноту перекладів перевіряють тести.
    """
    messages = MESSAGES.get(code, MESSAGES["internal_error"])
    return messages.get(locale, messages[DEFAULT_LOCALE])
