"""add use_ai and ai_prompt to automation_steps

Revision ID: 0024_add_ai_prompt_to_steps
Revises: 0023_add_bot_instructions
Create Date: 2026-06-05 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_add_ai_prompt_to_steps"
down_revision = "0023_add_bot_instructions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "automation_steps",
        sa.Column("use_ai", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "automation_steps",
        sa.Column("ai_prompt", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("automation_steps", "ai_prompt")
    op.drop_column("automation_steps", "use_ai")
