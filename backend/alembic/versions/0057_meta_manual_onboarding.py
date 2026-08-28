"""meta_* columns for the self-service manual WhatsApp onboarding: the
advertiser's own Meta App (app_id + encrypted app_secret) so the server can
configure that app's webhook via the Graph API and validate its inbound
signatures, plus number-verification bookkeeping (status + encrypted 2FA PIN)
used by the later OTP flow.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_app_id", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("meta_app_secret_cipher", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("meta_app_secret_iv", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("meta_app_secret_tag", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "meta_webhook_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Number verification sub-flow — populated by the later OTP endpoints
    # (Fase B). Columns land now so 0057 is the only migration this feature needs.
    op.add_column(
        "users",
        sa.Column(
            "meta_verification_status",
            sa.String(20),
            nullable=False,
            server_default="not_started",
        ),
    )
    op.add_column("users", sa.Column("meta_pin_cipher", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("meta_pin_iv", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("meta_pin_tag", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "meta_pin_tag")
    op.drop_column("users", "meta_pin_iv")
    op.drop_column("users", "meta_pin_cipher")
    op.drop_column("users", "meta_verification_status")
    op.drop_column("users", "meta_webhook_configured")
    op.drop_column("users", "meta_app_secret_tag")
    op.drop_column("users", "meta_app_secret_iv")
    op.drop_column("users", "meta_app_secret_cipher")
    op.drop_column("users", "meta_app_id")
