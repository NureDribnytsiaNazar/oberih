"""Початкові тарифи, незмінність журналів, індекси під типові запити.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 23:50:18
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Тарифні плани з таблиці 4 Vision & Scope. Ціни орієнтовні (див.
# docs/assumptions.md), «багато об'єктів» обмежено значенням 100.
TARIFFS = [
    {
        "code": "basic",
        "name": "Базовий",
        "price_month": Decimal("0.00"),
        "max_facilities": 1,
        "archive_days": 7,
        "email_notifications": False,
        "guest_access": False,
        "false_alarm_stats": False,
        "incident_timeline": False,
        "api_access": False,
    },
    {
        "code": "standard",
        "name": "Стандартний",
        "price_month": Decimal("4.99"),
        "max_facilities": 3,
        "archive_days": 90,
        "email_notifications": True,
        "guest_access": True,
        "false_alarm_stats": True,
        "incident_timeline": False,
        "api_access": False,
    },
    {
        "code": "professional",
        "name": "Професійний",
        "price_month": Decimal("14.99"),
        "max_facilities": 100,
        "archive_days": 730,
        "email_notifications": True,
        "guest_access": True,
        "false_alarm_stats": True,
        "incident_timeline": True,
        "api_access": True,
    },
]

# Таблиця журналу -> (батьківська таблиця, стовпець зовнішнього ключа).
# Видалити запис журналу можна лише каскадно разом із батьківським записом
# (наприклад, коли власник видаляє об'єкт); audit_log не видаляється взагалі.
APPEND_ONLY_TABLES: dict[str, tuple[str, str] | None] = {
    "arming_log": ("facilities", "facility_id"),
    "alarm_acknowledgements": ("alarms", "alarm_id"),
    "audit_log": None,
}

FORBID_LOG_CHANGE_SQL = """
CREATE FUNCTION forbid_log_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_exists boolean;
BEGIN
    IF TG_OP = 'DELETE' AND TG_NARGS = 2 THEN
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)',
                       TG_ARGV[0])
            INTO parent_exists
            USING (to_jsonb(OLD) ->> TG_ARGV[1])::uuid;
        IF NOT parent_exists THEN
            RETURN OLD;
        END IF;
    END IF;
    RAISE EXCEPTION 'Table % is append-only: % is not allowed',
        TG_TABLE_NAME, TG_OP;
END;
$$;
"""


def upgrade() -> None:
    """Застосовує зміни схеми."""
    op.create_index(
        "ix_alarms_facility_status", "alarms", ["facility_id", "status"]
    )
    op.create_index(
        "ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"]
    )
    op.create_unique_constraint(
        op.f("uq_nodes_device_token_hash"), "nodes", ["device_token_hash"]
    )

    op.execute(FORBID_LOG_CHANGE_SQL)
    for table, parent in APPEND_ONLY_TABLES.items():
        args = f"'{parent[0]}', '{parent[1]}'" if parent else ""
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only "
            f"BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION forbid_log_change({args})"
        )

    tariff_table = sa.table(
        "tariff_plans",
        sa.column("id", sa.Uuid),
        *(sa.column(name) for name in TARIFFS[0]),
    )
    op.bulk_insert(tariff_table, [{"id": uuid.uuid4(), **row} for row in TARIFFS])


def downgrade() -> None:
    """Скасовує зміни схеми."""
    codes = ", ".join(f"'{row['code']}'" for row in TARIFFS)
    op.execute(f"DELETE FROM tariff_plans WHERE code IN ({codes})")

    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION forbid_log_change()")

    op.drop_constraint(op.f("uq_nodes_device_token_hash"), "nodes", type_="unique")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_alarms_facility_status", table_name="alarms")
