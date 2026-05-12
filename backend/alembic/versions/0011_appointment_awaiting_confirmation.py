"""add awaiting_confirmation to appointments

Revision ID: 0011_appt_confirm
Revises: 0010_appointments
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_appt_confirm"
down_revision = "0010_appointments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("awaiting_confirmation", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("appointments", "awaiting_confirmation")
