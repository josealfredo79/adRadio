"""Seguimiento automático de interesados (followup_service.py, spec
docs/specs/2026-10-15-seguimiento-automatico.md).

- users.followup_enabled: el dueño lo puede apagar en Configuración (encendido por defecto).
- contacts.last_followup_at: un seguimiento por cliente por semana como máximo.

Revision ID: 0075
Revises: 0074
Create Date: 2026-10-15
"""
import sqlalchemy as sa

from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("followup_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("contacts", sa.Column("last_followup_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "last_followup_at")
    op.drop_column("users", "followup_enabled")
