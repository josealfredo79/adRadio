"""Bot Closer: per-advertiser closer_config on users, and coupon provenance
(source) + a one-shot reminder timestamp on coupons.

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("closer_config", postgresql.JSONB(), nullable=True))
    op.add_column(
        "coupons",
        sa.Column("source", sa.String(20), nullable=False, server_default="campaign"),
    )
    op.add_column("coupons", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    # Backfill: coupons linked from a customer story are the Voces VIP coupons.
    op.execute(
        "UPDATE coupons SET source = 'voces' "
        "WHERE id IN (SELECT coupon_id FROM customer_stories WHERE coupon_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_column("coupons", "reminder_sent_at")
    op.drop_column("coupons", "source")
    op.drop_column("users", "closer_config")
