"""Push subscriptions: navegadores de clientes que aceptaron notificaciones
web desde el portal del cliente — avisos gratis en vez de WhatsApp cobrado.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "advertiser_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_subscriptions_advertiser_id", "push_subscriptions", ["advertiser_id"])
    op.create_index("ix_push_subscriptions_contact_id", "push_subscriptions", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_contact_id", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_advertiser_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
