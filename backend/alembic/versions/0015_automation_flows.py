"""add automation flows/steps/enrollments tables

Revision ID: 0015_automation_flows
Revises: 0014_team_members
Create Date: 2025-01-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_automation_flows"
down_revision = "0014_team_members"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False, server_default="new_contact"),
        sa.Column("trigger_value", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("trigger IN ('new_contact','keyword','tag_added')", name="ck_automation_flows_trigger"),
    )
    op.create_index("ix_automation_flows_advertiser", "automation_flows", ["advertiser_id"])

    op.create_table(
        "automation_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automation_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delay_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_automation_steps_flow", "automation_steps", ["flow_id"])

    op.create_table(
        "automation_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automation_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("advertiser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_step", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_enrollments_flow", "automation_enrollments", ["flow_id"])
    op.create_index("ix_automation_enrollments_contact", "automation_enrollments", ["contact_id"])


def downgrade():
    op.drop_table("automation_enrollments")
    op.drop_table("automation_steps")
    op.drop_table("automation_flows")
