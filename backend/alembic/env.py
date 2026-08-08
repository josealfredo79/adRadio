from logging.config import fileConfig
import asyncio

from sqlalchemy import event, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models so Alembic can detect them
from app.models.user import User  # noqa: F401
from app.models.contact import Contact  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.knowledge_base import KnowledgeBase  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.coupon import Coupon  # noqa: F401
from app.models.customer_story import CustomerStory  # noqa: F401
from app.models.user_webhook import UserWebhook  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.lab import LabRun, LabConversation  # noqa: F401
from app.database import Base, _set_search_path
from app.config import settings

config = context.config

_sync_url = settings.database_url_safe
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


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    event.listens_for(connectable.sync_engine, "connect")(_set_search_path)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
