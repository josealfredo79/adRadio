"""Agente del cliente encendido para todos: users.customer_agent_enabled pasa
a true en los negocios que ya existen y es el valor por defecto de los nuevos.
Probado de punta a punta en producción el 2026-10-15 (cita, pedido y
cancelaciones). Cada dueño lo puede apagar en Configuración.

Revision ID: 0074
Revises: 0073
Create Date: 2026-10-15
"""
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "customer_agent_enabled", server_default="true")
    op.execute("UPDATE users SET customer_agent_enabled = true WHERE customer_agent_enabled = false")


def downgrade() -> None:
    op.alter_column("users", "customer_agent_enabled", server_default="false")
