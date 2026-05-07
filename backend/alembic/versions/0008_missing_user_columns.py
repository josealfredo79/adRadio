"""Add missing user columns

Revision ID: 0008_missing_user_columns
Revises: 0007_voyage_embedding_1024
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_missing_user_columns"
down_revision = "0007_voyage_embedding_1024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verification_token", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("business_category", sa.String(100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("logo_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("phone", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "logo_url")
    op.drop_column("users", "business_category")
    op.drop_column("users", "email_verification_token")
