"""add pipeline_stage to contacts (kanban)

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("pipeline_stage", sa.String(20), nullable=False, server_default="nuevo"),
    )
    op.create_check_constraint(
        "ck_contacts_pipeline_stage",
        "contacts",
        "pipeline_stage IN ('nuevo','conversacion','interesado','cliente','perdido')",
    )
    op.create_index("ix_contacts_pipeline_stage", "contacts", ["advertiser_id", "pipeline_stage"])


def downgrade() -> None:
    op.drop_index("ix_contacts_pipeline_stage", table_name="contacts")
    op.drop_constraint("ck_contacts_pipeline_stage", "contacts", type_="check")
    op.drop_column("contacts", "pipeline_stage")
