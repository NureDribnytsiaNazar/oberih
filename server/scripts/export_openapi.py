"""Експорт специфікації OpenAPI у docs/openapi.json.

Запуск із каталогу server:
    python -m scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import app

TARGET = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def main() -> None:
    """Записує актуальну специфікацію API у файл."""
    spec = app.openapi()
    TARGET.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Специфікацію записано: {TARGET} ({len(spec['paths'])} шляхів)")


if __name__ == "__main__":
    main()
