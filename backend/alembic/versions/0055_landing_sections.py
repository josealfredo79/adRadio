"""landing_sections — ordered, filtered list of visible landing-page section ids

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("landing_sections", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "landing_sections")
