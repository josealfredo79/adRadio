"""Add missing FK indexes for performance

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Index names already created by migration 0020 (via raw SQL with IF NOT EXISTS).
# We use IF NOT EXISTS here too so this migration is idempotent.
_INDEXES = [
    # Single-column FK indexes
    "ix_contacts_advertiser_id",
    "ix_campaigns_advertiser_id",
    "ix_messages_campaign_id",
    "ix_messages_contact_id",
    "ix_conversations_advertiser_id",
    "ix_conversations_contact_id",
    "ix_knowledge_base_advertiser_id",
    "ix_coupons_campaign_id",
    "ix_coupons_contact_id",
    "ix_customer_stories_contact_id",
    "ix_customer_stories_campaign_id",
    "ix_user_webhooks_user_id",
    "ix_message_templates_advertiser_id",
    # Composite indexes
    "ix_contacts_advertiser_id_status",
    "ix_conversations_advertiser_id_status",
    "ix_messages_advertiser_id_direction",
    "ix_messages_advertiser_id_contact_id",
    "ix_messages_campaign_id_status",
]

_TABLE_COLUMN = {
    "ix_contacts_advertiser_id": ("contacts", ["advertiser_id"]),
    "ix_campaigns_advertiser_id": ("campaigns", ["advertiser_id"]),
    "ix_messages_campaign_id": ("messages", ["campaign_id"]),
    "ix_messages_contact_id": ("messages", ["contact_id"]),
    "ix_conversations_advertiser_id": ("conversations", ["advertiser_id"]),
    "ix_conversations_contact_id": ("conversations", ["contact_id"]),
    "ix_knowledge_base_advertiser_id": ("knowledge_base", ["advertiser_id"]),
    "ix_coupons_campaign_id": ("coupons", ["campaign_id"]),
    "ix_coupons_contact_id": ("coupons", ["contact_id"]),
    "ix_customer_stories_contact_id": ("customer_stories", ["contact_id"]),
    "ix_customer_stories_campaign_id": ("customer_stories", ["campaign_id"]),
    "ix_user_webhooks_user_id": ("user_webhooks", ["user_id"]),
    "ix_message_templates_advertiser_id": ("message_templates", ["advertiser_id"]),
    "ix_contacts_advertiser_id_status": ("contacts", ["advertiser_id", "status"]),
    "ix_conversations_advertiser_id_status": ("conversations", ["advertiser_id", "status"]),
    "ix_messages_advertiser_id_direction": ("messages", ["advertiser_id", "direction"]),
    "ix_messages_advertiser_id_contact_id": ("messages", ["advertiser_id", "contact_id"]),
    "ix_messages_campaign_id_status": ("messages", ["campaign_id", "status"]),
}


def upgrade() -> None:
    for ix_name in _INDEXES:
        table, columns = _TABLE_COLUMN[ix_name]
        cols_sql = ", ".join(columns)
        op.execute(f"CREATE INDEX IF NOT EXISTS {ix_name} ON {table} ({cols_sql})")


def downgrade() -> None:
    for ix_name in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {ix_name}")
