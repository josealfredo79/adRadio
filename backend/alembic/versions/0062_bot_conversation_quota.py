"""Cuota de conversaciones del bot por plan (rediseño de planes 2026-10-01):
contador mensual, paquetes extra comprados y nivel de aviso enviado.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-01
"""
import sqlalchemy as sa

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bot_conv_month", sa.String(7), nullable=True))
    op.add_column("users", sa.Column("bot_conv_used", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("bot_conv_extra", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("bot_conv_alert", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "bot_conv_alert")
    op.drop_column("users", "bot_conv_extra")
    op.drop_column("users", "bot_conv_used")
    op.drop_column("users", "bot_conv_month")
