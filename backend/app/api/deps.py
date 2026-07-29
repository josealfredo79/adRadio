"""
Dependency: current authenticated user + plan-based feature gating.
"""
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def _user_from_access_token(token: str | None, db: AsyncSession) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    return await _user_from_access_token(token, db)


async def get_current_user_sse(
    token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Same as get_current_user, but also accepts the access token as a `token`
    query param — the browser's native EventSource API can't attach a custom
    Authorization header, so SSE endpoints need this. Only use this for SSE
    routes, never for regular JSON endpoints (query strings end up in server
    logs/browser history).
    """
    bearer_token = credentials.credentials if credentials else None
    return await _user_from_access_token(token or bearer_token, db)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return user


# ─── Feature Gating ─────────────────────────────────────────────────────────

# Plan hierarchy (higher = more features)
PLAN_ORDER = ["trial", "starter", "growth", "pro", "business", "enterprise"]

# Minimum plan required for each feature
FEATURE_PLAN = {
    "rag": "growth",           # Bot con catálogo (RAG)
    "radio_cuna": "growth",    # Cuñas de radio
    "sequence": "pro",         # Campañas secuencia (3 mensajes)
    "saga": "business",        # Campañas saga (4 episodios)
    "ab_testing": "business",  # A/B testing
    "api_access": "business",  # API de integración
    "white_label": "enterprise", # White-label
    "multi_number": "enterprise", # Multi-número WhatsApp
}

# Maximum radio ads per billing period (-1 = unlimited)
PLAN_RADIO_LIMITS = {
    "trial": 3,
    "starter": 0,
    "growth": 3,
    "pro": -1,
    "business": -1,
    "enterprise": -1,
}


def _plan_index(plan: str) -> int:
    try:
        return PLAN_ORDER.index(plan)
    except ValueError:
        return 0


def check_feature_access(user: User, feature: str) -> bool:
    """Check if user's plan includes a feature."""
    required_plan = FEATURE_PLAN.get(feature)
    if not required_plan:
        return True  # feature not gated
    return _plan_index(user.current_plan or "trial") >= _plan_index(required_plan)


async def require_feature(feature: str, user: User = Depends(get_current_user)) -> User:
    """Dependency: raise 402 if the user's plan doesn't include the feature."""
    if not check_feature_access(user, feature):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Tu plan {user.current_plan} no incluye esta función. Actualiza tu plan para acceder.",
        )
    return user


def get_radio_limit(user: User) -> int:
    """Returns max radio ads per billing period (-1 = unlimited)."""
    return PLAN_RADIO_LIMITS.get(user.current_plan or "trial", 0)
