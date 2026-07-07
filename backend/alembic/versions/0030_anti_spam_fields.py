"""add anti-spam fields to contacts

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("last_campaign_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("failed_send_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "contacts",
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "suppressed_until")
    op.drop_column("contacts", "failed_send_count")
    op.drop_column("contacts", "last_campaign_sent_at")
