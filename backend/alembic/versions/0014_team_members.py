"""add team_members table

Revision ID: 0014_team_members
Revises: 0013_message_templates
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_team_members"
down_revision = "0013_message_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="agent"),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_team_members_owner", "team_members", ["owner_id"])


def downgrade():
    op.drop_index("ix_team_members_owner", table_name="team_members")
    op.drop_table("team_members")
