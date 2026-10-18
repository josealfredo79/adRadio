"""Ventas del negocio: "Cobré $___" del mostrador y pedidos con monto
(app/models/sale.py, spec docs/specs/2026-10-17-cobre.md). Solo crea la tabla.

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("source", sa.String(10), nullable=False, server_default="counter"),
        sa.Column("source_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_sales_amount_positive"),
        sa.CheckConstraint("source IN ('counter','order')", name="ck_sales_source"),
    )
    op.create_index("ix_sales_advertiser_created", "sales", ["advertiser_id", "created_at"])
    op.create_index("ix_sales_contact_id", "sales", ["contact_id"])
    op.create_index("uq_sales_order", "sales", ["advertiser_id", "source", "source_key"], unique=True,
                    postgresql_where=sa.text("source = 'order'"))


def downgrade() -> None:
    op.drop_table("sales")
