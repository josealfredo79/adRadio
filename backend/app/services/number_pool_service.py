"""
Number Pool Service — manages dedicated WhatsApp numbers from a DB-backed pool.

Pool numbers are stored in the `pool_numbers` table and can be managed
via admin endpoints without redeploying.

Assignment logic:
  1. Read active numbers from the DB pool.
  2. On first use, if the DB pool is empty, seed it from TWILIO_NUMBER_POOL env var.
  3. Pick the first available one or assign a specific number.
  4. If no numbers are available, user stays on 'shared' mode.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pool_number import PoolNumber
from app.models.user import User

logger = logging.getLogger(__name__)


async def _get_active_pool_numbers(db: AsyncSession) -> list[str]:
    """Return active pool numbers from DB. Seeds from env var if empty."""
    result = await db.execute(
        select(PoolNumber.number).where(PoolNumber.is_active == True)
    )
    rows = result.fetchall()
    numbers = [row[0] for row in rows]

    if not numbers and settings.TWILIO_NUMBER_POOL:
        env_numbers = settings.twilio_number_pool_list
        for n in env_numbers:
            db.add(PoolNumber(number=n, label="Migrado desde TWILIO_NUMBER_POOL"))
        await db.flush()
        numbers = env_numbers
        logger.info("Seeded %d pool numbers from TWILIO_NUMBER_POOL env var", len(env_numbers))

    return numbers


async def _get_assigned_numbers(db: AsyncSession) -> set[str]:
    """Return set of pool numbers currently assigned to users."""
    result = await db.execute(
        select(User.whatsapp_number).where(
            User.whatsapp_number_source == "pool",
            User.whatsapp_number.isnot(None),
        )
    )
    rows = result.fetchall()
    return {row[0] for row in rows}


async def assign_pool_number(user: User, db: AsyncSession) -> bool:
    """
    Try to assign a free pool number to the user.
    Returns True if a number was assigned, False if pool is exhausted.
    """
    pool = await _get_active_pool_numbers(db)
    if not pool:
        logger.warning("Pool is empty — no numbers available to assign.")
        return False

    assigned = await _get_assigned_numbers(db)
    free_number = next((n for n in pool if n not in assigned), None)

    if not free_number:
        logger.warning("Pool exhausted — all %d numbers are assigned.", len(pool))
        return False

    user.whatsapp_number = free_number
    user.whatsapp_number_source = "pool"
    await db.flush()
    logger.info("Assigned pool number %s to user %s (%s)", free_number, user.id, user.email)
    return True


async def assign_specific_pool_number(user: User, db: AsyncSession, number: str) -> bool:
    """
    Assign a specific pool number to the user.
    Validates the number is in the pool and not already assigned.
    Returns True if assigned, False if the number is invalid or already taken.
    """
    pool = await _get_active_pool_numbers(db)
    if number not in pool:
        logger.warning("Number %s is not in the pool", number)
        return False

    assigned = await _get_assigned_numbers(db)
    if number in assigned:
        # Check if it's assigned to this same user (no-op)
        result = await db.execute(
            select(User).where(
                User.whatsapp_number == number,
                User.whatsapp_number_source == "pool",
                User.id != user.id,
            )
        )
        if result.scalar_one_or_none():
            logger.warning("Number %s is already assigned to another user", number)
            return False

    # Release current pool number if the user has one
    if user.whatsapp_number_source == "pool" and user.whatsapp_number:
        await release_pool_number(user, db)

    user.whatsapp_number = number
    user.whatsapp_number_source = "pool"
    await db.flush()
    logger.info("Assigned specific pool number %s to user %s (%s)", number, user.id, user.email)
    return True


async def release_pool_number(user: User, db: AsyncSession) -> None:
    """
    Release a pool number back when a user cancels or downgrades.
    """
    if user.whatsapp_number_source == "pool" and user.whatsapp_number:
        released = user.whatsapp_number
        user.whatsapp_number = None
        user.whatsapp_number_source = "shared"
        await db.flush()
        logger.info("Released pool number %s from user %s", released, user.id)


async def pool_status(db: AsyncSession) -> dict:
    """Return current pool usage for admin dashboard."""
    pool = await _get_active_pool_numbers(db)
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


async def add_pool_number(db: AsyncSession, number: str, label: str | None = None) -> PoolNumber:
    """Add a new number to the pool. Returns the created PoolNumber or raises if duplicate."""
    existing = await db.execute(
        select(PoolNumber).where(PoolNumber.number == number)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Number {number} already exists in the pool")

    entry = PoolNumber(number=number, label=label)
    db.add(entry)
    await db.flush()
    logger.info("Added pool number %s (label=%s)", number, label)
    return entry


async def remove_pool_number(db: AsyncSession, number: str) -> bool:
    """Soft-delete a number from the pool (sets is_active=False). Returns True if found."""
    result = await db.execute(
        select(PoolNumber).where(PoolNumber.number == number)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return False

    # Check if it's currently assigned to someone
    assigned = await _get_assigned_numbers(db)
    if number in assigned:
        raise ValueError(f"Cannot remove number {number} — it is currently assigned to a user. Release it first.")

    entry.is_active = False
    await db.flush()
    logger.info("Removed pool number %s", number)
    return True


async def list_pool_numbers(db: AsyncSession, include_inactive: bool = False) -> list[dict]:
    """List all pool numbers with their assignment status."""
    query = select(PoolNumber)
    if not include_inactive:
        query = query.where(PoolNumber.is_active == True)
    query = query.order_by(PoolNumber.number)

    result = await db.execute(query)
    entries = result.scalars().all()

    assigned = await _get_assigned_numbers(db)

    return [
        {
            "id": str(e.id),
            "number": e.number,
            "label": e.label,
            "is_active": e.is_active,
            "status": "assigned" if e.number in assigned else "free",
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
