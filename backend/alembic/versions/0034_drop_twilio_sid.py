"""drop messages.twilio_sid — Twilio fully retired, wa_message_id is now the only channel id

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_messages_twilio_sid_unique", table_name="messages")
    op.drop_column("messages", "twilio_sid")


def downgrade() -> None:
    op.add_column("messages", sa.Column("twilio_sid", sa.String(50), nullable=True))
    op.create_index(
        "ix_messages_twilio_sid_unique",
        "messages",
        ["twilio_sid"],
        unique=True,
        postgresql_where=sa.text("twilio_sid IS NOT NULL"),
    )
