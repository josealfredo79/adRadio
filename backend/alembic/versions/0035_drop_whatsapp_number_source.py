"""drop users.whatsapp_number_source — shared/pool tiers retired with Twilio

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "whatsapp_number_source")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("whatsapp_number_source", sa.String(10), nullable=False, server_default="shared"),
    )
