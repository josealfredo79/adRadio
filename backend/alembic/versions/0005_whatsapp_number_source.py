"""add whatsapp_number_source to users

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_whatsapp_number_source"
down_revision = "0004_kb_processing_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "whatsapp_number_source",
            sa.String(10),
            nullable=False,
            server_default="shared",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "whatsapp_number_source")
