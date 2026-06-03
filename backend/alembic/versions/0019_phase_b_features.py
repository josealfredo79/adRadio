"""add user_webhooks, api_keys, white_label column

Revision ID: 0019_phase_b_features
Revises: 0018_widget_customization
Create Date: 2026-06-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0019_phase_b_features"
down_revision = "0018_widget_customization"
branch_labels = None
depends_on = None


def upgrade():
    # White-label column on users
    op.add_column("users", sa.Column("white_label", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))

    # User webhooks table
    op.create_table(
        "user_webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("events", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # API keys table
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(op.f("ix_api_keys_prefix"), "api_keys", ["prefix"])
    op.create_index(op.f("ix_user_webhooks_user_id"), "user_webhooks", ["user_id"])
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"])


def downgrade():
    op.drop_table("api_keys")
    op.drop_table("user_webhooks")
    op.drop_column("users", "white_label")
