from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,       # 3 servicios × 5 = 15 conexiones — seguro en Neon free tier
    max_overflow=10,   # burst máximo de 15 conexiones extra en picos
    pool_recycle=300,  # recicla conexiones antes del timeout idle de Neon (~5 min)
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Engine sin pool para Celery workers (cada tarea crea su propia conexión en su event loop)
_celery_engine = None


def _get_celery_engine():
    global _celery_engine
    if _celery_engine is None:
        _celery_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            poolclass=NullPool,
        )
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
