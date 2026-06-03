"""
API Keys management router — /api/v1/api-keys
"""
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


API_KEY_PREFIX = "iar_"


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: str | None = None
    active: bool
    created_at: str

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    key: str
    active: bool
    created_at: str

    model_config = {"from_attributes": True}


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_key = f"{API_KEY_PREFIX}{secrets.token_hex(30)}"
    prefix = raw_key[:8]

    api_key = ApiKey(
        user_id=current_user.id,
        name=body.name,
        key=raw_key,
        prefix=prefix,
        scopes=body.scopes,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    out = ApiKeyCreatedOut.model_validate(api_key)
    out.key = raw_key
    return out


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
    )
    return [ApiKeyOut.model_validate(k) for k in result.scalars().all()]


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key no encontrada")
    await db.delete(api_key)
    await db.commit()


@router.patch("/{key_id}/deactivate", response_model=ApiKeyOut)
async def deactivate_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key no encontrada")
    api_key.active = False
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyOut.model_validate(api_key)
