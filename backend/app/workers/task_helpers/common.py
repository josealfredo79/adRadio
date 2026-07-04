"""
Common utilities for Celery tasks.
"""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession


def run_async(coro):
    """Helper to run async code in sync Celery task."""
    async def _wrapped():
        try:
            return await coro
        finally:
            from app.database import _get_celery_engine
            await _get_celery_engine().dispose()
    return asyncio.run(_wrapped())


async def _get_advertiser_whatsapp_number(db: AsyncSession, advertiser_id: uuid.UUID) -> str | None:
    from app.models.user import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == advertiser_id))
    advertiser = result.scalar_one_or_none()
    return advertiser.whatsapp_number if advertiser else None
