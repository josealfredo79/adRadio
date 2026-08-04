"""drop prospects_pool — dead table, ProspectsPool model was never used
by any router, service, task, or test

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("prospects_pool")


def downgrade() -> None:
    op.create_table(
        "prospects_pool",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255)),
        sa.Column("interests", postgresql.ARRAY(sa.String())),
        sa.Column("city", sa.String(100)),
        sa.Column("country", sa.String(10)),
        sa.Column("language", sa.String(5)),
        sa.Column("opt_in_source", sa.String(255)),
        sa.Column("opt_in_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opt_in_proof_url", sa.Text(), nullable=False),
        sa.Column("available", sa.Boolean()),
        sa.Column("times_used", sa.Integer()),
        sa.Column("last_contact", sa.DateTime(timezone=True)),
    )
