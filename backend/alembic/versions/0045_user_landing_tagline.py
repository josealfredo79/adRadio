"""users.landing_tagline — short welcome line for the AdRadio-hosted landing page

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("landing_tagline", sa.String(140), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "landing_tagline")
