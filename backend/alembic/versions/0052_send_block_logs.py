"""send_block_logs table — audit trail of sends blocked by anti-ban/compliance gates

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "send_block_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "advertiser_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_send_block_logs_advertiser_id", "send_block_logs", ["advertiser_id"])
    op.create_index("ix_send_block_logs_campaign_id", "send_block_logs", ["campaign_id"])
    op.create_index("ix_send_block_logs_contact_id", "send_block_logs", ["contact_id"])
    op.create_index("ix_send_block_logs_created_at", "send_block_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_send_block_logs_created_at", table_name="send_block_logs")
    op.drop_index("ix_send_block_logs_contact_id", table_name="send_block_logs")
    op.drop_index("ix_send_block_logs_campaign_id", table_name="send_block_logs")
    op.drop_index("ix_send_block_logs_advertiser_id", table_name="send_block_logs")
    op.drop_table("send_block_logs")
