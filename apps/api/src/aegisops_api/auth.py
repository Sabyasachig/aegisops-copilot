"""JWT authentication helpers and FastAPI dependency.

Provides:
- ``hash_password`` / ``verify_password``  – bcrypt wrappers
- ``create_access_token`` / ``create_refresh_token``  – signed JWTs
- ``get_current_user``  – FastAPI dependency that validates a Bearer token
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import get_db
from .db.repository import get_user_by_username
from .settings import get_settings

# tokenUrl is shown in OpenAPI docs — must match the login endpoint path.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=True)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* value."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(username: str) -> tuple[str, int]:
    """Return ``(access_token, expires_in_seconds)``."""
    settings = get_settings()
    expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    token = _create_token(username, expires, "access")
    return token, int(expires.total_seconds())


def create_refresh_token(username: str) -> str:
    """Return a long-lived refresh token."""
    settings = get_settings()
    expires = timedelta(days=settings.jwt_refresh_token_expire_days)
    return _create_token(username, expires, "refresh")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Validate a Bearer JWT and return the authenticated username.

    Raises ``HTTP 401`` if the token is missing, malformed, expired, or the
    referenced user does not exist / is inactive.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise exc
        username: str | None = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc

    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise exc

    return username
