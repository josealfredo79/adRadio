"""Add unique constraint on messages.twilio_sid (partial, non-null only)

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-06 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_twilio_sid_unique",
        "messages",
        ["twilio_sid"],
        unique=True,
        postgresql_where=sa.text("twilio_sid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_twilio_sid_unique", table_name="messages")
