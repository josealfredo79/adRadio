"""founder_program — cupos del programa "Fundadores" (precio bloqueado para
los primeros clientes en Starter/Growth) + users.is_founder

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-09
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

FOUNDER_SLOTS_TOTAL = 25


def upgrade() -> None:
    op.create_table(
        "founder_program",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slots_total", sa.Integer(), nullable=False),
        sa.Column("slots_used", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "founder_program",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("slots_total", sa.Integer()),
            sa.column("slots_used", sa.Integer()),
        ),
        [{"id": uuid.uuid4(), "slots_total": FOUNDER_SLOTS_TOTAL, "slots_used": 0}],
    )
    op.add_column("users", sa.Column("is_founder", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "is_founder")
    op.drop_table("founder_program")
