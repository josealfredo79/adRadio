"""Voces del Barrio — emotional loop: moderation status (pending/approved/
rejected), recorded consent for publishing the customer's voice + first name,
publish timestamp, and a link to the VIP coupon issued when the story was sent.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_stories",
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("customer_stories", sa.Column("consent_text", sa.Text(), nullable=True))
    op.add_column("customer_stories", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customer_stories", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "customer_stories",
        sa.Column(
            "coupon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coupons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Backfill: the old bare `approved` boolean maps onto the new status enum.
    op.execute(
        "UPDATE customer_stories SET status = CASE WHEN approved THEN 'approved' ELSE 'pending' END"
    )


def downgrade() -> None:
    op.drop_column("customer_stories", "coupon_id")
    op.drop_column("customer_stories", "published_at")
    op.drop_column("customer_stories", "consent_at")
    op.drop_column("customer_stories", "consent_text")
    op.drop_column("customer_stories", "status")
