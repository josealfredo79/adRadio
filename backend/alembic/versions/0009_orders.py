"""Add orders table

Revision ID: 0009_orders
Revises: 0008_missing_user_columns
Create Date: 2026-05-11
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_orders"
down_revision = "0008_missing_user_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
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
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("order_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(30), nullable=False, server_default="collecting_name"),
        sa.Column("items_raw", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_orders_advertiser_id", "orders", ["advertiser_id"])
    op.create_index("ix_orders_contact_id", "orders", ["contact_id"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_contact_id", table_name="orders")
    op.drop_index("ix_orders_advertiser_id", table_name="orders")
    op.drop_table("orders")
