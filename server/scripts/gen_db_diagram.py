"""Генерація діаграми структури БД (PlantUML) з метаданих моделей.

Діаграма будується з тих самих моделей, що й міграції, тому завжди
відповідає коду. Запуск із каталогу server:
    python -m scripts.gen_db_diagram
"""

from pathlib import Path

from sqlalchemy import Column, Enum, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.models import Base

TARGET = Path(__file__).resolve().parents[2] / "docs" / "diagrams" / "db-structure.puml"
DIALECT = postgresql.dialect()


def column_type(column: Column[object]) -> str:
    """Назва типу стовпця так, як її створює PostgreSQL."""
    if isinstance(column.type, Enum):
        return f"enum {column.type.name}"
    return str(column.type.compile(dialect=DIALECT)).lower()


def column_line(table: Table, column: Column[object]) -> str:
    """Рядок стовпця: обов'язкові позначені *, ключі — стереотипами."""
    marks = []
    if column.primary_key:
        marks.append("PK")
    if column.foreign_keys:
        marks.append("FK")
    unique_single = any(
        len(constraint.columns) == 1 and column.name in constraint.columns
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    if column.unique or unique_single:
        marks.append("UK")
    prefix = "* " if not column.nullable else "  "
    suffix = f" <<{', '.join(marks)}>>" if marks else ""
    return f"  {prefix}{column.name} : {column_type(column)}{suffix}"


def render() -> str:
    """Текст діаграми PlantUML для всіх таблиць і зв'язків."""
    lines = [
        "@startuml db-structure",
        "' Згенеровано scripts/gen_db_diagram.py — не редагувати вручну.",
        "!pragma layout smetana",
        "hide circle",
        "skinparam linetype ortho",
        "skinparam shadowing false",
        "skinparam defaultFontName Arial",
        "title Структура бази даних «Оберіг» (PostgreSQL 16)",
        "",
    ]
    relations = []
    for table in Base.metadata.sorted_tables:
        lines.append(f'entity "{table.name}" as {table.name} {{')
        keys = [c for c in table.columns if c.primary_key]
        others = [c for c in table.columns if not c.primary_key]
        lines.extend(column_line(table, column) for column in keys)
        lines.append("  --")
        lines.extend(column_line(table, column) for column in others)
        lines.append("}")
        lines.append("")
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                # Необов'язковий зв'язок (nullable FK) — «нуль або один».
                end = "o|" if column.nullable else "||"
                relations.append(f"{table.name} }}o--{end} {parent}")
    lines.extend(sorted(set(relations)))
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Записує діаграму у docs/diagrams/db-structure.puml."""
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8")
    print(f"Діаграму записано: {TARGET}")


if __name__ == "__main__":
    main()
