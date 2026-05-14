"""
Auth router — /api/v1/auth
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email import send_verification_email, send_password_reset_email
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_verification_code,
    generate_secure_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.services.number_pool_service import assign_pool_number
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        business_name=body.business_name,
        email_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate 6-digit code and store in Redis
    code = generate_verification_code()
    await redis.setex(f"email_verify:{user.email}", settings.EMAIL_VERIFICATION_TTL, code)
    await send_verification_email(user.email, code)

    return {"message": "Registro exitoso. Revisa tu email para verificar tu cuenta."}


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    stored_code = await redis.get(f"email_verify:{body.email}")
    if not stored_code or stored_code != body.code:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.email_verified = True
    # Grant trial credits on first verification
    if user.messages_remaining == 0:
        user.messages_remaining = 50
    await db.commit()

    # Assign a pool number if available (enables inbound bot for this user)
    await assign_pool_number(user, db)

    await redis.delete(f"email_verify:{body.email}")

    return {"message": "Email verificado correctamente"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Debes verificar tu email primero")

    if user.subscription_status == "suspended":
        raise HTTPException(status_code=403, detail="Cuenta suspendida. Contacta soporte.")

    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))

    # Store refresh token in Redis (rotation)
    await redis.setex(
        f"refresh:{str(user.id)}",
        settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        refresh_token,
    )

    # Set refresh_token as httpOnly cookie (not accessible via JS)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    # Accept refresh_token from httpOnly cookie (primary) or request body (backward compat)
    token = request.cookies.get("refresh_token") or (body.refresh_token if body else None)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token requerido")

    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    user_id = payload.get("sub")
    stored = await redis.get(f"refresh:{user_id}")
    if stored != token:
        raise HTTPException(status_code=401, detail="Refresh token revocado")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    access_token = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id))

    # Rotate refresh token in Redis
    await redis.setex(
        f"refresh:{user_id}",
        settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        new_refresh,
    )

    # Rotate the httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    redis=Depends(get_redis),
):
    token = request.cookies.get("refresh_token") or (body.refresh_token if body else None)
    if token:
        payload = decode_token(token)
        if payload and payload.get("sub"):
            await redis.delete(f"refresh:{payload['sub']}")
    response.delete_cookie("refresh_token", path="/api/v1/auth", httponly=True)
    return {"message": "Sesión cerrada"}


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        token = generate_secure_token()
        await redis.setex(f"pwd_reset:{token}", 3600, str(user.id))
        await send_password_reset_email(user.email, token)
    # Always return 200 to avoid email enumeration
    return {"message": "Si el email existe, recibirás un enlace para restablecer tu contraseña"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    user_id = await redis.get(f"pwd_reset:{body.token}")
    if not user_id:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await redis.delete(f"pwd_reset:{body.token}")
    # Invalidate all refresh tokens
    await redis.delete(f"refresh:{user_id}")

    return {"message": "Contraseña restablecida correctamente"}
