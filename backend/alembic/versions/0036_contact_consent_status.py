"""contacts.consent_status — block cold-window template sends to unverified CSV imports

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("consent_status", sa.String(20), nullable=False, server_default="confirmed"),
    )
    op.create_check_constraint(
        "ck_contacts_consent_status",
        "contacts",
        "consent_status IN ('confirmed','unconfirmed')",
    )
    # Backfill: CSV-imported contacts who never replied have no verified consent.
    # Everyone else (manual entry, landing/referral, or anyone who already
    # messaged in) keeps the 'confirmed' default — they're not the cold-list
    # abuse pattern this column exists to block.
    op.execute(
        """
        UPDATE contacts
        SET consent_status = 'unconfirmed'
        WHERE source = 'csv'
          AND NOT EXISTS (
              SELECT 1 FROM messages
              WHERE messages.contact_id = contacts.id
                AND messages.direction = 'inbound'
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_consent_status", "contacts", type_="check")
    op.drop_column("contacts", "consent_status")
