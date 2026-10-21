"""Entrega a domicilio sí/no del negocio (spec docs/specs/2026-10-20-entrega-a-domicilio.md).
Vacío = sin definir: el bot ofrece solo "para recoger". Solo agrega la columna.

Revision ID: 0077
Revises: 0076
Create Date: 2026-10-20
"""
import sqlalchemy as sa

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("delivers_home", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "delivers_home")
