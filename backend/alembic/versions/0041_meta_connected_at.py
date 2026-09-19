"""users.meta_connected_at — track when the current WhatsApp number was
connected, to drive the warm-up ramp (Capa 11 anti-baneo)

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-30
"""
import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_connected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "meta_connected_at")
