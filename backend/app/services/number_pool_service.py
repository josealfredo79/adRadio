"""
Number Pool Service — assigns a dedicated WhatsApp number from the pool to a new advertiser.

Pool numbers are defined in .env as TWILIO_NUMBER_POOL (comma-separated).
Each number can only be assigned to one advertiser at a time.

Assignment logic:
  1. Look for available numbers in the pool (not yet assigned to any user).
  2. Pick the first available one.
  3. Assign it to the user (whatsapp_number = number, whatsapp_number_source = 'pool').
  4. If no numbers are available, user stays on 'shared' mode.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


async def assign_pool_number(user: User, db: AsyncSession) -> bool:
    """
    Try to assign a free pool number to the user.
    Returns True if a number was assigned, False if pool is exhausted.
    """
    pool = settings.twilio_number_pool_list
    if not pool:
        logger.warning("TWILIO_NUMBER_POOL is empty — no numbers available to assign.")
        return False

    # Get all numbers already assigned from the pool
    result = await db.execute(
        select(User.whatsapp_number).where(
            User.whatsapp_number_source == "pool",
            User.whatsapp_number.isnot(None),
        )
    )
    assigned = {row[0] for row in result.fetchall()}

    # Find first free number
    free_number = next((n for n in pool if n not in assigned), None)

    if not free_number:
        logger.warning("Pool exhausted — all %d numbers are assigned.", len(pool))
        return False

    user.whatsapp_number = free_number
    user.whatsapp_number_source = "pool"
    await db.commit()
    await db.refresh(user)
    logger.info("Assigned pool number %s to user %s (%s)", free_number, user.id, user.email)
    return True


async def release_pool_number(user: User, db: AsyncSession) -> None:
    """
    Release a pool number back when a user cancels or downgrades.
    """
    if user.whatsapp_number_source == "pool" and user.whatsapp_number:
        released = user.whatsapp_number
        user.whatsapp_number = None
        user.whatsapp_number_source = "shared"
        await db.commit()
        logger.info("Released pool number %s from user %s", released, user.id)


async def pool_status(db: AsyncSession) -> dict:
    """Return current pool usage for admin dashboard."""
    pool = settings.twilio_number_pool_list
    if not pool:
        return {"total": 0, "assigned": 0, "free": 0, "numbers": []}

    result = await db.execute(
        select(User.whatsapp_number, User.email, User.business_name).where(
            User.whatsapp_number_source == "pool",
            User.whatsapp_number.isnot(None),
        )
    )
    rows = result.fetchall()
    assigned_map = {row[0]: {"email": row[1], "business": row[2]} for row in rows}

    numbers = [
        {
            "number": n,
            "status": "assigned" if n in assigned_map else "free",
            "advertiser": assigned_map.get(n),
        }
        for n in pool
    ]
    return {
        "total": len(pool),
        "assigned": len(assigned_map),
        "free": len(pool) - len(assigned_map),
        "numbers": numbers,
    }
