"""hero_image_url — optional cover photo for the public landing page header

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("hero_image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "hero_image_url")
