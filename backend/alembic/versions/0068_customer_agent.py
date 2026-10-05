"""Agente del cliente (customer_agent.py): users.customer_agent_enabled — el
negocio enciende el agente con herramientas (citas, pedidos, sellos) en su
chat web. Apagado por defecto mientras está en beta.

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-05
"""
import sqlalchemy as sa

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("customer_agent_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "customer_agent_enabled")
