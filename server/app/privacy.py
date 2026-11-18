"""Відомості про оброблювані персональні дані (GDPR, ст. 13; ФМ-11).

Тексти двома мовами; строки зберігання подій беруться з тарифних планів.
"""

from dataclasses import dataclass

from app.models.enums import Locale


@dataclass(frozen=True)
class DataCategory:
    """Категорія даних: що зберігається, навіщо і як довго."""

    code: str
    data: str
    purpose: str
    retention: str


@dataclass(frozen=True)
class DataRight:
    """Право суб'єкта даних і спосіб його реалізації в API."""

    code: str
    description: str
    endpoint: str


CATEGORIES: dict[Locale, list[DataCategory]] = {
    Locale.UK: [
        DataCategory(
            "account",
            "Електронна пошта, ім'я, хеш пароля, мова, часовий пояс, згода",
            "Автентифікація та налаштування інтерфейсу",
            "До видалення облікового запису (після нього — знеособлення)",
        ),
        DataCategory(
            "facility",
            "Об'єкти, зони, вузли, датчики, розклади, учасники та їхні ролі",
            "Надання послуги охорони",
            "До видалення об'єкта власником",
        ),
        DataCategory(
            "events",
            "Події датчиків і тривоги з мітками часу",
            "Виявлення проникнення, статистика хибних спрацювань",
            "За тарифом власника об'єкта (див. retention_by_tariff)",
        ),
        DataCategory(
            "journals",
            "Журнал постановки й зняття, підтвердження тривог, журнал аудиту",
            "Підзвітність дій користувачів і адміністраторів",
            "Зберігаються без змін; після видалення облікового запису "
            "посилаються на знеособлений запис",
        ),
        DataCategory(
            "incidents",
            "Стисла хронологія інциденту без імен користувачів",
            "Пояснення тривоги (лише факти датчиків і припущення)",
            "Разом із тривогою",
        ),
    ],
    Locale.EN: [
        DataCategory(
            "account",
            "Email, name, password hash, language, time zone, consent",
            "Authentication and interface preferences",
            "Until account deletion (then anonymized)",
        ),
        DataCategory(
            "facility",
            "Facilities, zones, nodes, sensors, schedules, members and roles",
            "Providing the security service",
            "Until the owner deletes the facility",
        ),
        DataCategory(
            "events",
            "Sensor events and alarms with timestamps",
            "Intrusion detection, false alarm statistics",
            "According to the facility owner's tariff (see retention_by_tariff)",
        ),
        DataCategory(
            "journals",
            "Arming log, alarm acknowledgements, audit log",
            "Accountability of user and administrator actions",
            "Kept unchanged; after account deletion they refer to an "
            "anonymized record",
        ),
        DataCategory(
            "incidents",
            "Short incident timeline without user names",
            "Explaining an alarm (sensor facts and assumptions only)",
            "Together with the alarm",
        ),
    ],
}

RIGHTS: dict[Locale, list[DataRight]] = {
    Locale.UK: [
        DataRight("access", "Отримати копію всіх своїх даних", "GET /users/me/export"),
        DataRight("rectification", "Виправити дані профілю", "PATCH /users/me"),
        DataRight(
            "erasure", "Видалити обліковий запис (знеособлення)", "DELETE /users/me"
        ),
    ],
    Locale.EN: [
        DataRight("access", "Get a copy of all your data", "GET /users/me/export"),
        DataRight("rectification", "Correct profile data", "PATCH /users/me"),
        DataRight("erasure", "Delete the account (anonymization)", "DELETE /users/me"),
    ],
}
