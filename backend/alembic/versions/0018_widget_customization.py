"""add widget customization columns to users

Revision ID: 0018_widget_customization
Revises: 0017_add_voces_campaign_type
Create Date: 2026-06-03 00:00:02.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_widget_customization"
down_revision = "0017_add_voces_campaign_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("widget_color", sa.String(7), nullable=False, server_default="#25D366"))
    op.add_column("users", sa.Column("widget_greeting", sa.String(200), nullable=False, server_default="¡Hola! ¿En qué puedo ayudarte?"))
    op.add_column("users", sa.Column("widget_position", sa.String(10), nullable=False, server_default="right"))


def downgrade():
    op.drop_column("users", "widget_position")
    op.drop_column("users", "widget_greeting")
    op.drop_column("users", "widget_color")
