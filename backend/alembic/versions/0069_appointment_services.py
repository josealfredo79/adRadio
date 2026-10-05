"""Servicios con duración (users.appointment_services): [{"name", "minutes"}].
El agente del cliente aparta el tiempo de cada servicio (un tinte 120 min, un
corte 30) en vez de 30 min fijos. Null = todo dura 30 min, como antes.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("appointment_services", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "appointment_services")
