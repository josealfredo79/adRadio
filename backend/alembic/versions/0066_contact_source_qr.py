"""contacts.source — add 'qr' for customers who sign up themselves from the
business's counter QR (api/v1/join.py), with their number confirmed by a
WhatsApp code.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-04
"""
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_source",
        "contacts",
        "source IN ('manual','csv','landing','referral','widget','qr')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_source",
        "contacts",
        "source IN ('manual','csv','landing','referral','widget')",
    )
