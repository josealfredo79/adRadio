"""Add city column to contacts

Revision ID: 0003_contact_city
Revises: 0002_coupons
Create Date: 2026-05-06 00:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_contact_city"
down_revision: Union[str, None] = "0002_coupons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("city", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "city")
