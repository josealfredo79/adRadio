"""
API Key authentication dependency.
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User

api_key_scheme = HTTPBearer()


async def get_user_from_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(api_key_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    key = credentials.credentials
    prefix = key[:8]

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.prefix == prefix,
            ApiKey.active == True,  # noqa: E712
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida",
        )

    if not verify_api_key(key, api_key.key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida",
        )

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )
    return user


def require_api_key_scope(required_scope: str):
    """Dependency factory that validates the API key has the required scope."""
    async def _check(
        credentials: HTTPAuthorizationCredentials = Depends(api_key_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        key = credentials.credentials
        prefix = key[:8]

        result = await db.execute(
            select(ApiKey).where(
                ApiKey.prefix == prefix,
                ApiKey.active == True,  # noqa: E712
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=401, detail="API key inválida")

        if not verify_api_key(key, api_key.key):
            raise HTTPException(status_code=401, detail="API key inválida")

        if required_scope not in (api_key.scopes or []):
            raise HTTPException(
                status_code=403,
                detail=f"API key no tiene permiso: {required_scope}",
            )

        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        user_result = await db.execute(select(User).where(User.id == api_key.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return user

    return _check
