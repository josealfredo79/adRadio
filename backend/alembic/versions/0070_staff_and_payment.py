"""Personal que atiende las citas y cómo cobra el negocio.

- users.staff: [{"name": "Lupita", "services": ["Corte de dama"]}] — services
  vacío = hace todo. Con personal, caben tantas citas a la misma hora como
  personas libres (availability_service).
- appointments.staff_name: con quién es la cita (null = sin asignar).
- users.payment_link / users.payment_transfer: el link de cobro del negocio
  (Mercado Pago, Stripe, Clip…) y sus datos de transferencia; el agente los
  manda al confirmar un pedido con tarjeta o transferencia.

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("staff", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("payment_link", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("payment_transfer", sa.String(500), nullable=True))
    op.add_column("appointments", sa.Column("staff_name", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("appointments", "staff_name")
    op.drop_column("users", "payment_transfer")
    op.drop_column("users", "payment_link")
    op.drop_column("users", "staff")
