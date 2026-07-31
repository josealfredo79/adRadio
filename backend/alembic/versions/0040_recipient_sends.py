"""recipient_sends — enforce Meta's messaging_limit_tier as a hard cap on unique recipients per rolling 24h window (Capa 10 anti-baneo)

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipient_sends",
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
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_recipient_sends_advertiser_sent_at", "recipient_sends", ["advertiser_id", "sent_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_recipient_sends_advertiser_sent_at", table_name="recipient_sends")
    op.drop_table("recipient_sends")
