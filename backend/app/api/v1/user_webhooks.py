"""
User Webhooks router — /api/v1/user-webhooks
"""
import logging
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_webhook import UserWebhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-webhooks", tags=["user-webhooks"])


class UserWebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str]


class UserWebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    active: bool | None = None


class UserWebhookOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    events: list[str]
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TestPingResult(BaseModel):
    success: bool
    status_code: int | None = None
    error: str | None = None


@router.get("", response_model=list[UserWebhookOut])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserWebhookOut]:
    result = await db.execute(
        select(UserWebhook).where(UserWebhook.user_id == current_user.id)
    )
    return [UserWebhookOut.model_validate(w) for w in result.scalars().all()]


@router.post("", response_model=UserWebhookOut, status_code=201)
async def create_webhook(
    body: UserWebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserWebhookOut:
    webhook = UserWebhook(
        user_id=current_user.id,
        name=body.name,
        url=body.url,
        events=body.events,
        secret=secrets.token_hex(32),
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return UserWebhookOut.model_validate(webhook)


@router.patch("/{webhook_id}", response_model=UserWebhookOut)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: UserWebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserWebhookOut:
    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.id == webhook_id,
            UserWebhook.user_id == current_user.id,
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook no encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(wh, field, value)
    await db.commit()
    await db.refresh(wh)
    return UserWebhookOut.model_validate(wh)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.id == webhook_id,
            UserWebhook.user_id == current_user.id,
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook no encontrado")
    await db.delete(wh)
    await db.commit()


@router.post("/{webhook_id}/test", response_model=TestPingResult)
async def test_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestPingResult:
    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.id == webhook_id,
            UserWebhook.user_id == current_user.id,
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook no encontrado")

    from app.services.webhook_dispatcher import _sign_body
    import json
    from datetime import datetime, timezone
    import httpx

    body_data = {
        "event": "test.ping",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "Test ping from IaRadio"},
    }
    body_bytes = json.dumps(body_data).encode("utf-8")
    signature = _sign_body(wh.secret, body_bytes)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                wh.url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Event": "test.ping",
                    "User-Agent": "IaRadio-Webhook/1.0",
                },
            )
        return TestPingResult(success=resp.is_success, status_code=resp.status_code)
    except Exception as exc:
        return TestPingResult(success=False, error=str(exc))
