"""Add processing_status to knowledge_base

Revision ID: 0004_kb_processing_status
Revises: 0003_contact_city
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_kb_processing_status"
down_revision = "0003_contact_city"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base",
        sa.Column(
            "processing_status",
            sa.String(20),
            nullable=False,
            server_default="processing",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_base", "processing_status")
