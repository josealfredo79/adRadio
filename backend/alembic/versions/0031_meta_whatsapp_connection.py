"""add Meta Cloud API connection fields to users, wa_message_id to messages

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_waba_id", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("meta_phone_number_id", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("meta_display_phone_number", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("meta_verified_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("meta_token_cipher", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("meta_token_iv", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("meta_token_tag", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "meta_connection_status",
            sa.String(20),
            nullable=False,
            server_default="not_connected",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "meta_utility_template_status",
            sa.String(20),
            nullable=False,
            server_default="not_configured",
        ),
    )
    op.add_column("users", sa.Column("meta_utility_template_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("meta_appointment_template_name", sa.String(255), nullable=True))

    op.create_index(
        "ix_users_meta_phone_number_id_unique",
        "users",
        ["meta_phone_number_id"],
        unique=True,
        postgresql_where=sa.text("meta_phone_number_id IS NOT NULL"),
    )

    op.add_column("messages", sa.Column("wa_message_id", sa.String(100), nullable=True))
    op.create_index(
        "ix_messages_wa_message_id_unique",
        "messages",
        ["wa_message_id"],
        unique=True,
        postgresql_where=sa.text("wa_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_wa_message_id_unique", table_name="messages")
    op.drop_column("messages", "wa_message_id")

    op.drop_index("ix_users_meta_phone_number_id_unique", table_name="users")
    op.drop_column("users", "meta_appointment_template_name")
    op.drop_column("users", "meta_utility_template_name")
    op.drop_column("users", "meta_utility_template_status")
    op.drop_column("users", "meta_connection_status")
    op.drop_column("users", "meta_token_tag")
    op.drop_column("users", "meta_token_iv")
    op.drop_column("users", "meta_token_cipher")
    op.drop_column("users", "meta_verified_name")
    op.drop_column("users", "meta_display_phone_number")
    op.drop_column("users", "meta_phone_number_id")
    op.drop_column("users", "meta_waba_id")
