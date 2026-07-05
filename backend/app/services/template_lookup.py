"""
Look up message templates by advertiser, category, and step.
Falls back to None when no template exists — caller uses hardcoded default.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import MessageTemplate


async def get_template(
    db: AsyncSession,
    advertiser_id: str,
    category: str,
    step: str,
) -> str | None:
    """Return the template content for a given advertiser + category + step, or None."""
    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.advertiser_id == advertiser_id,
            MessageTemplate.category == category,
            MessageTemplate.step == step,
        ).limit(1)
    )
    tpl = result.scalar_one_or_none()
    return tpl.content if tpl else None
