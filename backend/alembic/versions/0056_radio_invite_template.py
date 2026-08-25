"""meta_radio_invite_template_name — opt-in template (with Si/No buttons) for
offering a radio cuña to a contact with a closed 24h window.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_radio_invite_template_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "meta_radio_invite_template_name")
