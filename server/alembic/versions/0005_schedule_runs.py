"""Виконання розкладів: момент останнього спрацювання розкладу.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Застосовує зміни схеми."""
    op.add_column(
        "schedules",
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Скасовує зміни схеми."""
    op.drop_column("schedules", "last_run_at")
