import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with cost factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    token = secrets.token_urlsafe(64)
    payload = {
        "sub": subject,
        "jti": token,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_verification_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def hash_api_key(key: str) -> str:
    """Hash an API key with bcrypt for storage."""
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(key.encode("utf-8"), salt).decode("utf-8")


def verify_api_key(plain_key: str, stored_key: str) -> bool:
    """Verify an API key against its stored hash.

    Supports both bcrypt (new) and SHA-256 (legacy) formats.
    """
    if stored_key.startswith("$2"):
        return bcrypt.checkpw(plain_key.encode("utf-8"), stored_key.encode("utf-8"))
    import hashlib
    return hashlib.sha256(plain_key.encode()).hexdigest() == hashlib.sha256(stored_key.encode()).hexdigest()
