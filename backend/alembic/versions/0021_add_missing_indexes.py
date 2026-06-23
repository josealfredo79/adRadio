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
    op.execute('CREATE INDEX IF NOT EXISTS ix_messages_advertiser_id ON messages (advertiser_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_messages_direction ON messages (direction)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_messages_scheduled_for ON messages (scheduled_for)')

    # transactions - commonly filtered by advertiser and sorted by created_at
    op.execute('CREATE INDEX IF NOT EXISTS ix_transactions_advertiser_id ON transactions (advertiser_id)')

    # automation_enrollments - commonly filtered by advertiser and status
    op.execute('CREATE INDEX IF NOT EXISTS ix_automation_enrollments_advertiser_id ON automation_enrollments (advertiser_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_automation_enrollments_status ON automation_enrollments (status)')

    # coupons - commonly filtered by advertiser
    op.execute('CREATE INDEX IF NOT EXISTS ix_coupons_advertiser_id ON coupons (advertiser_id)')

    # conversations - commonly sorted by last_activity
    op.execute('CREATE INDEX IF NOT EXISTS ix_conversations_last_activity ON conversations (last_activity)')

    # api_keys - commonly filtered by user_id
    op.execute('CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id)')

    # customer_stories - commonly filtered by advertiser
    op.execute('CREATE INDEX IF NOT EXISTS ix_customer_stories_advertiser_id ON customer_stories (advertiser_id)')


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
