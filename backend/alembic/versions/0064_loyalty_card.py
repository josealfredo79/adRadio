"""Tarjeta de lealtad del portal del cliente: config del negocio
(users.loyalty_config) y un sello por fila (loyalty_stamps).

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("loyalty_config", postgresql.JSONB(), nullable=True))
    op.create_table(
        "loyalty_stamps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "advertiser_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("contact_id", "source", "source_key", name="uq_loyalty_stamp_source"),
    )
    op.create_index("ix_loyalty_stamps_advertiser_id", "loyalty_stamps", ["advertiser_id"])
    op.create_index("ix_loyalty_stamps_contact_id", "loyalty_stamps", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_loyalty_stamps_contact_id", table_name="loyalty_stamps")
    op.drop_index("ix_loyalty_stamps_advertiser_id", table_name="loyalty_stamps")
    op.drop_table("loyalty_stamps")
    op.drop_column("users", "loyalty_config")
