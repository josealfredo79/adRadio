"""add voces campaign type to check constraint

Revision ID: 0017_add_voces_campaign_type
Revises: 0016_customer_stories
Create Date: 2026-06-03 00:00:01.000000
"""
from alembic import op

revision = "0017_add_voces_campaign_type"
down_revision = "0016_customer_stories"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS ck_campaigns_type")
    op.execute(
        "ALTER TABLE campaigns ADD CONSTRAINT ck_campaigns_type "
        "CHECK (type IN ('promo','reminder','launch','event','voces'))"
    )


def downgrade():
    op.execute("ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS ck_campaigns_type")
    op.execute(
        "ALTER TABLE campaigns ADD CONSTRAINT ck_campaigns_type "
        "CHECK (type IN ('promo','reminder','launch','event'))"
    )
