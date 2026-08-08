"""users.business_hours — weekly schedule for self-service appointment booking

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("business_hours", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "business_hours")
