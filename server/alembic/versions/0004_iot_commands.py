"""IoT-клієнт: налаштування вузла, ключ підпису й черга команд (ЛБ4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMAND_TYPES = "'arm_away', 'arm_home', 'disarm', 'set_config'"
COMMAND_STATUSES = "'pending', 'delivered', 'acked', 'expired'"


def upgrade() -> None:
    """Застосовує зміни схеми."""
    op.add_column(
        "nodes",
        sa.Column("debounce_ms", sa.Integer(), server_default="50", nullable=False),
    )
    op.add_column(
        "nodes",
        sa.Column("pir_lockout_s", sa.Integer(), server_default="10", nullable=False),
    )
    op.add_column(
        "nodes",
        sa.Column("config_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "nodes", sa.Column("command_key", sa.LargeBinary(length=32), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_nodes_debounce_positive"), "nodes", "debounce_ms > 0"
    )
    op.create_check_constraint(
        op.f("ck_nodes_pir_lockout_non_negative"), "nodes", "pir_lockout_s >= 0"
    )
    op.create_check_constraint(
        op.f("ck_nodes_config_version_positive"), "nodes", "config_version > 0"
    )

    op.create_table(
        "node_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("nonce", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.CheckConstraint(
            f"command_type IN ({COMMAND_TYPES})",
            name=op.f("ck_node_commands_commandtype"),
        ),
        sa.CheckConstraint(
            f"status IN ({COMMAND_STATUSES})",
            name=op.f("ck_node_commands_commandstatus"),
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name=op.f("fk_node_commands_node_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_node_commands")),
        sa.UniqueConstraint("node_id", "nonce", name="uq_node_commands_node_nonce"),
    )
    op.create_index(
        op.f("ix_node_commands_node_id"), "node_commands", ["node_id"], unique=False
    )


def downgrade() -> None:
    """Скасовує зміни схеми."""
    op.drop_index(op.f("ix_node_commands_node_id"), table_name="node_commands")
    op.drop_table("node_commands")
    op.drop_constraint(op.f("ck_nodes_config_version_positive"), "nodes", type_="check")
    op.drop_constraint(
        op.f("ck_nodes_pir_lockout_non_negative"), "nodes", type_="check"
    )
    op.drop_constraint(op.f("ck_nodes_debounce_positive"), "nodes", type_="check")
    op.drop_column("nodes", "command_key")
    op.drop_column("nodes", "config_version")
    op.drop_column("nodes", "pir_lockout_s")
    op.drop_column("nodes", "debounce_ms")
