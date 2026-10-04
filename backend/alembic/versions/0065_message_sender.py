"""Quién escribió un mensaje saliente: NULL = el bot o una campaña, 'owner' =
el dueño desde el Inbox. El portal del cliente muestra las respuestas del
dueño como "te respondió {negocio}", no como del bot.

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-04
"""
import sqlalchemy as sa

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("sender", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "sender")
