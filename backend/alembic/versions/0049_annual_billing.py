"""users.billing_cycle + users.messages_refill_at — soporte para pago anual
con recarga mensual de mensajes desacoplada de la facturación de Stripe

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("billing_cycle", sa.String(10), nullable=False, server_default="monthly"),
    )
    op.add_column("users", sa.Column("messages_refill_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "messages_refill_at")
    op.drop_column("users", "billing_cycle")
