"""add lab_runs and lab_conversations (Laboratorio self-testing agent)

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running','completed','error')", name="ck_lab_runs_status"),
        sa.CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_lab_runs_score_range"),
    )
    op.create_index("ix_lab_runs_advertiser_id", "lab_runs", ["advertiser_id"])

    op.create_table(
        "lab_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lab_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona_key", sa.String(50), nullable=False),
        sa.Column("persona_label", sa.String(100), nullable=False),
        sa.Column("transcript", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("findings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_lab_conversations_score_range"),
    )
    op.create_index("ix_lab_conversations_lab_run_id", "lab_conversations", ["lab_run_id"])


def downgrade() -> None:
    op.drop_index("ix_lab_conversations_lab_run_id", table_name="lab_conversations")
    op.drop_table("lab_conversations")
    op.drop_index("ix_lab_runs_advertiser_id", table_name="lab_runs")
    op.drop_table("lab_runs")
