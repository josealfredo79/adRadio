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


def upgrade() -> None:
    # Single-column FK indexes
    op.create_index("ix_contacts_advertiser_id", "contacts", ["advertiser_id"])
    op.create_index("ix_campaigns_advertiser_id", "campaigns", ["advertiser_id"])
    op.create_index("ix_messages_campaign_id", "messages", ["campaign_id"])
    op.create_index("ix_messages_contact_id", "messages", ["contact_id"])
    op.create_index("ix_conversations_advertiser_id", "conversations", ["advertiser_id"])
    op.create_index("ix_conversations_contact_id", "conversations", ["contact_id"])
    op.create_index("ix_knowledge_base_advertiser_id", "knowledge_base", ["advertiser_id"])
    op.create_index("ix_coupons_campaign_id", "coupons", ["campaign_id"])
    op.create_index("ix_coupons_contact_id", "coupons", ["contact_id"])
    op.create_index("ix_customer_stories_contact_id", "customer_stories", ["contact_id"])
    op.create_index("ix_customer_stories_campaign_id", "customer_stories", ["campaign_id"])
    op.create_index("ix_user_webhooks_user_id", "user_webhooks", ["user_id"])
    op.create_index("ix_message_templates_advertiser_id", "message_templates", ["advertiser_id"])
    # Composite indexes for common query patterns
    op.create_index("ix_contacts_advertiser_id_status", "contacts", ["advertiser_id", "status"])
    op.create_index("ix_conversations_advertiser_id_status", "conversations", ["advertiser_id", "status"])
    op.create_index("ix_messages_advertiser_id_direction", "messages", ["advertiser_id", "direction"])
    op.create_index("ix_messages_advertiser_id_contact_id", "messages", ["advertiser_id", "contact_id"])
    op.create_index("ix_messages_campaign_id_status", "messages", ["campaign_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_contacts_advertiser_id")
    op.drop_index("ix_campaigns_advertiser_id")
    op.drop_index("ix_messages_campaign_id")
    op.drop_index("ix_messages_contact_id")
    op.drop_index("ix_conversations_advertiser_id")
    op.drop_index("ix_conversations_contact_id")
    op.drop_index("ix_knowledge_base_advertiser_id")
    op.drop_index("ix_coupons_campaign_id")
    op.drop_index("ix_coupons_contact_id")
    op.drop_index("ix_customer_stories_contact_id")
    op.drop_index("ix_customer_stories_campaign_id")
    op.drop_index("ix_user_webhooks_user_id")
    op.drop_index("ix_message_templates_advertiser_id")
    op.drop_index("ix_contacts_advertiser_id_status")
    op.drop_index("ix_conversations_advertiser_id_status")
    op.drop_index("ix_messages_advertiser_id_direction")
    op.drop_index("ix_messages_advertiser_id_contact_id")
    op.drop_index("ix_messages_campaign_id_status")
