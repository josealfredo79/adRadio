import threading

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

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

_celery_local = threading.local()


def _get_celery_engine():
    """Un motor por hilo del worker, sin grupo de conexiones (NullPool).

    El worker corre tareas en hilos (`--pool threads -c 4`, railway.json) y
    cada una con su propio asyncio.run (run_async). Un solo motor compartido
    entre hilos tronaba con "Lock ... is bound to a different event loop"
    (prod 13/14-oct, tareas del beat que caen en el mismo segundo) o se
    trababa para siempre — aun sin grupo de conexiones (comprobado con dos
    hilos: con un motor por hilo no pasa). Dentro de un hilo las tareas van
    una tras otra y NullPool evita reusar conexiones de un ciclo anterior."""
    engine = getattr(_celery_local, "engine", None)
    if engine is None:
        engine = create_async_engine(settings.database_url_safe, echo=settings.DEBUG, poolclass=NullPool)
        event.listens_for(engine.sync_engine, "connect")(_set_search_path)
        _celery_local.engine = engine
    return engine


def CeleryAsyncSessionLocal(**kwargs) -> AsyncSession:
    """Sesión para tareas de Celery, con el motor del hilo actual."""
    return AsyncSession(bind=_get_celery_engine(), expire_on_commit=False, **kwargs)


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
