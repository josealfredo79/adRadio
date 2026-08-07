"""contacts.source — add 'widget' for leads captured via the embeddable
website chat widget (independent of WhatsApp)

Along the way: ck_contacts_source turned out to never actually exist in the
live DB — the ORM model has declared this CheckConstraint since it was
added, but no prior migration ever created it (pure drift, same class of
bug documented elsewhere in this project's history). Verified live: every
existing row's source is 'manual', so creating the constraint fresh here is
safe — nothing to backfill.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-07
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_contacts_source",
        "contacts",
        "source IN ('manual','csv','landing','referral','widget')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
