"""add missing indexes for commonly queried columns

Revision ID: 0021_add_missing_indexes
Revises: 0020_add_performance_indexes
Create Date: 2026-06-04 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_add_missing_indexes"
down_revision = "0020_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # messages - commonly filtered by advertiser, direction, and scheduled_for
    op.create_index(op.f("ix_messages_advertiser_id"), "messages", ["advertiser_id"])
    op.create_index(op.f("ix_messages_direction"), "messages", ["direction"])
    op.create_index(op.f("ix_messages_scheduled_for"), "messages", ["scheduled_for"])

    # transactions - commonly filtered by advertiser and sorted by created_at
    op.create_index(
        op.f("ix_transactions_advertiser_id"), "transactions", ["advertiser_id"]
    )

    # automation_enrollments - commonly filtered by advertiser and status
    op.create_index(
        op.f("ix_automation_enrollments_advertiser_id"),
        "automation_enrollments",
        ["advertiser_id"],
    )
    op.create_index(
        op.f("ix_automation_enrollments_status"),
        "automation_enrollments",
        ["status"],
    )

    # coupons - commonly filtered by advertiser
    op.create_index(
        op.f("ix_coupons_advertiser_id"), "coupons", ["advertiser_id"]
    )

    # conversations - commonly sorted by last_activity
    op.create_index(
        op.f("ix_conversations_last_activity"),
        "conversations",
        ["last_activity"],
    )

    # api_keys - commonly filtered by user_id
    op.create_index(
        op.f("ix_api_keys_user_id"), "api_keys", ["user_id"]
    )

    # customer_stories - commonly filtered by advertiser
    op.create_index(
        op.f("ix_customer_stories_advertiser_id"),
        "customer_stories",
        ["advertiser_id"],
    )


def downgrade():
    op.drop_index(
        op.f("ix_customer_stories_advertiser_id"), table_name="customer_stories"
    )
    op.drop_index(op.f("ix_api_keys_user_id"), table_name="api_keys")
    op.drop_index(
        op.f("ix_conversations_last_activity"), table_name="conversations"
    )
    op.drop_index(
        op.f("ix_coupons_advertiser_id"), table_name="coupons"
    )
    op.drop_index(
        op.f("ix_automation_enrollments_status"),
        table_name="automation_enrollments",
    )
    op.drop_index(
        op.f("ix_automation_enrollments_advertiser_id"),
        table_name="automation_enrollments",
    )
    op.drop_index(
        op.f("ix_transactions_advertiser_id"), table_name="transactions"
    )
    op.drop_index(
        op.f("ix_messages_scheduled_for"), table_name="messages"
    )
    op.drop_index(op.f("ix_messages_direction"), table_name="messages")
    op.drop_index(
        op.f("ix_messages_advertiser_id"), table_name="messages"
    )
