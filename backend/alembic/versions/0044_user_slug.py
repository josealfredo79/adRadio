"""users.slug — URL slug for the AdRadio-hosted public landing page

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-07
"""
import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("slug", sa.String(60), nullable=True))
    op.create_unique_constraint("uq_users_slug", "users", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_users_slug", "users", type_="unique")
    op.drop_column("users", "slug")
