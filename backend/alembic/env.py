from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import all models so Alembic can detect them
from app.models.user import User  # noqa: F401
from app.models.contact import Contact  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.knowledge_base import KnowledgeBase  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.prospects_pool import ProspectsPool  # noqa: F401
from app.database import Base
from app.config import settings

config = context.config

# Convert asyncpg URL → psycopg2 for sync migrations
_sync_url = (
    settings.DATABASE_URL
    .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    .replace("postgresql+asyncpg+native://", "postgresql+psycopg2://")
    .replace("?ssl=require", "?sslmode=require")
    .replace("&ssl=require", "&sslmode=require")
)
config.set_main_option("sqlalchemy.url", _sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
