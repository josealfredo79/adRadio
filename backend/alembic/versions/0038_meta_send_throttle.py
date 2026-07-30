"""users.meta_send_throttle_per_hour — adaptive send cap (Propuesta 2 anti-baneo)

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("meta_send_throttle_per_hour", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("users", "meta_send_throttle_per_hour")
