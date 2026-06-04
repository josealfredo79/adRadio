"""add performance indexes for common query patterns

Revision ID: 0020_add_performance_indexes
Revises: 0019_phase_b_features
Create Date: 2026-06-03 12:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_add_performance_indexes"
down_revision = "0019_phase_b_features"
branch_labels = None
depends_on = None


def upgrade():
    # messages - commonly filtered by contact, campaign, and date range
    op.create_index(op.f("ix_messages_contact_id"), "messages", ["contact_id"])
    op.create_index(op.f("ix_messages_campaign_id"), "messages", ["campaign_id"])
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"])

    # contacts - commonly filtered by advertiser, status, tags, and date range
    op.create_index(op.f("ix_contacts_advertiser_id"), "contacts", ["advertiser_id"])
    op.create_index(op.f("ix_contacts_status"), "contacts", ["status"])
    op.create_index(
        op.f("ix_contacts_tags"), "contacts", ["tags"], postgresql_using="gin"
    )
    op.create_index(op.f("ix_contacts_created_at"), "contacts", ["created_at"])

    # campaigns - commonly filtered by advertiser, status, and date range
    op.create_index(op.f("ix_campaigns_advertiser_id"), "campaigns", ["advertiser_id"])
    op.create_index(op.f("ix_campaigns_status"), "campaigns", ["status"])
    op.create_index(op.f("ix_campaigns_created_at"), "campaigns", ["created_at"])

    # conversations - commonly filtered by contact, advertiser, and status
    op.create_index(
        op.f("ix_conversations_contact_id"), "conversations", ["contact_id"]
    )
    op.create_index(
        op.f("ix_conversations_advertiser_id"), "conversations", ["advertiser_id"]
    )
    op.create_index(op.f("ix_conversations_status"), "conversations", ["status"])

    # knowledge_base - commonly filtered by advertiser and processing status
    op.create_index(
        op.f("ix_knowledge_base_advertiser_id"), "knowledge_base", ["advertiser_id"]
    )
    op.create_index(
        op.f("ix_knowledge_base_processing_status"),
        "knowledge_base",
        ["processing_status"],
    )

    # team_members - commonly looked up by email
    op.create_index(
        op.f("ix_team_members_member_email"), "team_members", ["member_email"]
    )


def downgrade():
    op.drop_index(op.f("ix_team_members_member_email"), table_name="team_members")
    op.drop_index(
        op.f("ix_knowledge_base_processing_status"), table_name="knowledge_base"
    )
    op.drop_index(
        op.f("ix_knowledge_base_advertiser_id"), table_name="knowledge_base"
    )
    op.drop_index(op.f("ix_conversations_status"), table_name="conversations")
    op.drop_index(
        op.f("ix_conversations_advertiser_id"), table_name="conversations"
    )
    op.drop_index(
        op.f("ix_conversations_contact_id"), table_name="conversations"
    )
    op.drop_index(op.f("ix_campaigns_created_at"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_status"), table_name="campaigns")
    op.drop_index(
        op.f("ix_campaigns_advertiser_id"), table_name="campaigns"
    )
    op.drop_index(op.f("ix_contacts_created_at"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_tags"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_status"), table_name="contacts")
    op.drop_index(
        op.f("ix_contacts_advertiser_id"), table_name="contacts"
    )
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_campaign_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_contact_id"), table_name="messages")
