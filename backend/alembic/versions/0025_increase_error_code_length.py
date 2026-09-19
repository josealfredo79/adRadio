"""Increase error_code column length from 20 to 100

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-05 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("messages", "error_code", type_=sa.String(100))


def downgrade() -> None:
    op.alter_column("messages", "error_code", type_=sa.String(20))
