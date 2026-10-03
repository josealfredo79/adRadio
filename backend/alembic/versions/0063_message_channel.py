"""Canal de cada mensaje: NULL = WhatsApp (todo lo anterior), 'web' = el chat
del portal del cliente. Sirve para mostrarle al dueño cuántas respuestas se
dieron por la web en vez de WhatsApp (que Meta cobra desde 2026-10-01).

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-02
"""
import sqlalchemy as sa

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("channel", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "channel")
