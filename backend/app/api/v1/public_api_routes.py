"""
Public API endpoints — /api/v1/public/*
Authenticated via API key (Bearer token).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_key_auth import require_api_key_scope
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User
from app.schemas.campaign import CampaignOut
from app.schemas.contact import ContactListResponse, ContactOut

router = APIRouter(prefix="/public", tags=["public-api"])


@router.get("/campaigns")
async def public_list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_api_key_scope("campaigns:read")),
):
    q = select(Campaign).where(Campaign.advertiser_id == current_user.id)
    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    campaigns = result.scalars().all()

    return {
        "items": [CampaignOut.model_validate(c) for c in campaigns],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/contacts")
async def public_list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_api_key_scope("contacts:read")),
):
    q = select(Contact).where(Contact.advertiser_id == current_user.id)
    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    contacts = result.scalars().all()

    return ContactListResponse(
        items=[ContactOut.model_validate(c) for c in contacts],
        total=total,
        page=page,
        page_size=page_size,
    )
