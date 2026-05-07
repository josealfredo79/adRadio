"""Resize knowledge_base.embedding from 1536 to 3072 dims (text-embedding-3-large)

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic
revision = "0006_kb_embedding_3072"
down_revision = "0005_whatsapp_number_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old column and recreate with correct dimension.
    # We can't ALTER COLUMN for vector types, so drop + add is required.
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_base ADD COLUMN embedding vector(3072)")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_base ADD COLUMN embedding vector(1536)")
