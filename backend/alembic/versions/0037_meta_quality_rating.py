"""users.meta_quality_rating / meta_messaging_tier — track WABA health from Meta webhook events

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_quality_rating", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("meta_messaging_tier", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "meta_messaging_tier")
    op.drop_column("users", "meta_quality_rating")
