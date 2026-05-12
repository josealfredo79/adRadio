"""add appointments table and google calendar fields to users

Revision ID: 0010_appointments
Revises: 0009_orders
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_appointments"
down_revision = "0009_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Appointments table
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), index=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_phone", sa.String(30)),
        sa.Column("service", sa.String(300), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("duration_min", sa.Integer, default=30),
        sa.Column("notes", sa.Text),
        sa.Column("status", sa.String(20), default="pending", nullable=False, index=True),
        sa.Column("reminder_24h_sent", sa.Boolean, default=False),
        sa.Column("reminder_1h_sent", sa.Boolean, default=False),
        sa.Column("google_event_id", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # Google Calendar OAuth fields on users
    op.add_column("users", sa.Column("google_refresh_token", sa.Text, nullable=True))
    op.add_column("users", sa.Column("google_calendar_connected", sa.Boolean, server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "google_calendar_connected")
    op.drop_column("users", "google_refresh_token")
    op.drop_table("appointments")
