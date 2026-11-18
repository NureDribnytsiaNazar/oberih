"""Бізнес-логіка та адміністрування: статус користувача, формат часу, індекси.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 16:22:21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ALARM_STATUSES = "'open', 'acknowledged', 'resolved'"
NEW_ALARM_STATUSES = "'open', 'acknowledged', 'resolved', 'cancelled'"
DEDUP_COLUMNS = ["node_id", "sensor_id", "event_type", "seq"]


def upgrade() -> None:
    """Застосовує зміни схеми."""
    # Службові події вузла (node_offline/node_online) не мають датчика й
    # порядкового номера, тому NULL у ключі усунення дублікатів мають
    # вважатися різними значеннями (поведінка PostgreSQL за замовчуванням).
    op.drop_constraint(op.f("uq_events_dedup_key"), "events", type_="unique")
    op.create_unique_constraint(op.f("uq_events_dedup_key"), "events", DEDUP_COLUMNS)
    op.create_index(
        "ix_events_dedup_window", "events", ["sensor_id", "event_type", "occurred_at"]
    )

    op.drop_constraint(op.f("ck_alarms_alarmstatus"), "alarms", type_="check")
    op.create_check_constraint(
        op.f("ck_alarms_alarmstatus"), "alarms", f"status IN ({NEW_ALARM_STATUSES})"
    )

    op.add_column(
        "scenario_runs",
        sa.Column(
            "mismatches",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "time_format", sa.String(length=32), server_default="24h", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_timeformat"), "users", "time_format IN ('24h', '12h')"
    )
    op.add_column(
        "users", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Скасовує зміни схеми."""
    op.drop_column("users", "blocked_at")
    op.drop_constraint(op.f("ck_users_timeformat"), "users", type_="check")
    op.drop_column("users", "time_format")
    op.drop_column("scenario_runs", "mismatches")

    op.execute("UPDATE alarms SET status = 'resolved' WHERE status = 'cancelled'")
    op.drop_constraint(op.f("ck_alarms_alarmstatus"), "alarms", type_="check")
    op.create_check_constraint(
        op.f("ck_alarms_alarmstatus"), "alarms", f"status IN ({OLD_ALARM_STATUSES})"
    )

    op.drop_index("ix_events_dedup_window", table_name="events")
    # До 0003 службових подій вузла не було; без їх видалення старе обмеження
    # (NULLS NOT DISTINCT) не вдасться відновити.
    op.execute("DELETE FROM events WHERE seq IS NULL")
    op.drop_constraint(op.f("uq_events_dedup_key"), "events", type_="unique")
    op.create_unique_constraint(
        op.f("uq_events_dedup_key"),
        "events",
        DEDUP_COLUMNS,
        postgresql_nulls_not_distinct=True,
    )
