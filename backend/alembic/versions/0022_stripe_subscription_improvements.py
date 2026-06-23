"""add cancel_at_period_end, unique stripe_payment_id, transaction status constraint

Revision ID: 0022_stripe_subscription_improvements
Revises: 0021_add_missing_indexes
Create Date: 2026-06-04 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021_add_missing_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # Add cancel_at_period_end to users
    op.add_column(
        "users",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # Add unique constraint on stripe_payment_id for idempotency
    op.create_unique_constraint(
        "uq_transactions_stripe_payment_id",
        "transactions",
        ["stripe_payment_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_transactions_stripe_payment_id",
        "transactions",
        type_="unique",
    )
    op.drop_column("users", "cancel_at_period_end")
