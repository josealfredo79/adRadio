"""Switch knowledge_base embedding from 3072 (OpenAI) to 1024 dims (Voyage AI voyage-3)

Revision ID: 0007_voyage_embedding_1024
Revises: 0006_kb_embedding_3072
Create Date: 2026-05-06
"""
from alembic import op

revision = "0007_voyage_embedding_1024"
down_revision = "0006_kb_embedding_3072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old index and column, recreate with 1024 dims
    op.execute("DROP INDEX IF EXISTS ix_kb_embedding")
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_base ADD COLUMN embedding vector(1024)")
    op.execute("""
        CREATE INDEX ix_kb_embedding ON knowledge_base
        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_embedding")
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_base ADD COLUMN embedding vector(3072)")
    op.execute("""
        CREATE INDEX ix_kb_embedding ON knowledge_base
        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)
