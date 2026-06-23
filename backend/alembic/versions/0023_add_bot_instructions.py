"""add bot_instructions to users

Revision ID: 0023_add_bot_instructions
Revises: 0022_stripe_subscription_improvements
Create Date: 2026-06-05 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("bot_instructions", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("users", "bot_instructions")
