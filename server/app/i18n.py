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
    "alarm_closed": {
        Locale.UK: "Тривогу вже закрито",
        Locale.EN: "The alarm is already closed",
    },
}


def parse_accept_language(header: str | None) -> Locale:
    """Обирає мову з заголовка Accept-Language з урахуванням пріоритетів q."""
    if not header:
        return DEFAULT_LOCALE
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
    return DEFAULT_LOCALE


def translate(code: str, locale: Locale) -> str:
    """Повертає повідомлення для коду помилки потрібною мовою."""
    messages = MESSAGES.get(code, MESSAGES["internal_error"])
    return messages.get(locale, messages[DEFAULT_LOCALE])
