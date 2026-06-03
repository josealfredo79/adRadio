"""add customer_stories table

Revision ID: 0016_customer_stories
Revises: 0015_automation_flows
Create Date: 2026-06-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_customer_stories"
down_revision = "0015_automation_flows"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("media_url", sa.Text, nullable=False),
        sa.Column("transcription", sa.Text, nullable=False),
        sa.Column("sentiment", sa.String(20), nullable=False, server_default="neutro"),
        sa.Column("approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customer_stories_advertiser", "customer_stories", ["advertiser_id"])
    op.create_index("ix_customer_stories_campaign", "customer_stories", ["campaign_id"])


def downgrade():
    op.drop_table("customer_stories")
