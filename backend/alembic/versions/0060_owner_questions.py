"""Owner questions: preguntas de clientes que el bot reenvía al dueño por el
número central de IaRadio ("Déjame preguntarle al dueño").

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-24
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_questions",
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
        sa.Column("customer_phone", sa.String(20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("owner_wamid", sa.String(100), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_owner_questions_advertiser_id", "owner_questions", ["advertiser_id"])
    op.create_index("ix_owner_questions_owner_wamid", "owner_questions", ["owner_wamid"])


def downgrade() -> None:
    op.drop_index("ix_owner_questions_owner_wamid", table_name="owner_questions")
    op.drop_index("ix_owner_questions_advertiser_id", table_name="owner_questions")
    op.drop_table("owner_questions")
