"""Повнота перекладів: кожен код помилки має тексти uk і en."""

import re
from pathlib import Path

from app.i18n import MESSAGES
from app.models.enums import Locale

APP_DIR = Path(__file__).resolve().parent.parent / "app"
# Коди в конструкторах помилок: NotFoundError("code"), AppError(503, "code") тощо.
ERROR_CODE = re.compile(r'Error\((?:\d+,\s*)?"([a-z_.]+)"\)')
# Коди текстів, що перекладаються напряму: translate("far.check_sensor", ...).
TRANSLATED = re.compile(r'translate\(\s*"([a-z_.]+)"')
# Коди за замовчуванням у класах помилок: def __init__(self, code: str = "...").
DEFAULT_CODE = re.compile(r'code: str = "([a-z_.]+)"')


def used_codes() -> set[str]:
    codes: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        codes.update(ERROR_CODE.findall(source))
        codes.update(TRANSLATED.findall(source))
        codes.update(DEFAULT_CODE.findall(source))
    return codes


def test_every_used_code_is_translated() -> None:
    missing = sorted(code for code in used_codes() if code not in MESSAGES)
    assert missing == []


def test_every_message_has_all_locales() -> None:
    incomplete = sorted(
        code
        for code, texts in MESSAGES.items()
        if set(texts) != set(Locale) or not all(texts.values())
    )
    assert incomplete == []


def test_scanner_finds_codes() -> None:
    assert {"not_found", "tariff_limit", "backup_corrupted"} <= used_codes()
