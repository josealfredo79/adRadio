from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _set_search_path(dbapi_connection, connection_record):
    """Force search_path=public on every new physical connection.

    Neon's pooler endpoint has been observed handing out connections with
    an EMPTY search_path (not the normal Postgres default of "$user",
    public) — found 2026-08-06 when production logins started failing
    with "relation users does not exist" even though the table existed.
    asyncpg's `server_settings` connect_args does NOT survive the pooler
    (verified empirically: search_path still came back empty with it set);
    only an explicit SET after connecting works, via the asyncpg DBAPI
    adapter's run_async() bridge for the sync pool "connect" event.
    """
    dbapi_connection.run_async(lambda conn: conn.execute("SET search_path TO public"))


engine = create_async_engine(
    settings.database_url_safe,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=300,
)
event.listens_for(engine.sync_engine, "connect")(_set_search_path)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_celery_engine = None


def _get_celery_engine():
    global _celery_engine
    if _celery_engine is None:
        _celery_engine = create_async_engine(
            settings.database_url_safe,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=max(3, settings.DB_POOL_SIZE // 4),
            max_overflow=max(5, settings.DB_MAX_OVERFLOW // 2),
            pool_recycle=300,
        )
        event.listens_for(_celery_engine.sync_engine, "connect")(_set_search_path)
    return _celery_engine


CeleryAsyncSessionLocal = async_sessionmaker(
    _get_celery_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
