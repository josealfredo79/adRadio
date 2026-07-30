"""campaign_segment_sends — block relaunching the same list/segment within N days (Propuesta 4 anti-baneo)

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_segment_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "advertiser_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_fingerprint", sa.String(64), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("advertiser_id", "segment_fingerprint", name="uq_campaign_segment_sends_advertiser_fingerprint"),
    )
    op.create_index(
        "ix_campaign_segment_sends_advertiser_id", "campaign_segment_sends", ["advertiser_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_segment_sends_advertiser_id", table_name="campaign_segment_sends")
    op.drop_table("campaign_segment_sends")
