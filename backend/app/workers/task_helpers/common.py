"""
Common utilities for Celery tasks.
"""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession


def run_async(coro):
    """Helper to run async code in sync Celery task."""
    return asyncio.run(coro)


async def _get_advertiser_whatsapp_number(db: AsyncSession, advertiser_id: uuid.UUID) -> str | None:
    from app.models.user import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == advertiser_id))
    advertiser = result.scalar_one_or_none()
    return advertiser.whatsapp_number if advertiser else None
