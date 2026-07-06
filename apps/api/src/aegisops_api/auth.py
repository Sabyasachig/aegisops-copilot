"""JWT authentication helpers and role-based access control dependencies.

Provides:
- ``hash_password`` / ``verify_password``  — bcrypt wrappers
- ``create_access_token`` / ``create_refresh_token``  — signed JWTs
- ``require_role(role)``  — factory returning a FastAPI dependency
- ``require_viewer``  — dependency: any authenticated user (viewer+)
- ``require_operator``  — dependency: operator or admin
- ``require_admin``  — dependency: admin only
- ``get_current_user``  — alias for ``require_viewer`` (backward-compatible)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import get_db
from .db.orm_models import UserRow
from .db.repository import get_user_by_username
from .settings import get_settings

# tokenUrl is shown in OpenAPI docs — must match the login endpoint path.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=True)

# Role hierarchy — higher rank = more permissions
_ROLE_RANK: dict[str, int] = {"viewer": 1, "operator": 2, "admin": 3}


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
# Internal auth helper
# ---------------------------------------------------------------------------


async def _authenticate(token: str, db: AsyncSession) -> UserRow:
    """Decode a Bearer JWT and return the active ``UserRow``. Raises 401 on failure."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        settings = get_settings()
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
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
    return user


# ---------------------------------------------------------------------------
# Role-based dependency factory
# ---------------------------------------------------------------------------


def require_role(minimum_role: str):
    """Return a FastAPI dependency that enforces *minimum_role*.

    The returned callable validates the Bearer token, fetches the user, and
    checks that ``user.role`` ranks at or above *minimum_role* in the
    viewer → operator → admin hierarchy.  Raises:

    - ``HTTP 401`` — missing / invalid / expired token
    - ``HTTP 403`` — authenticated but insufficient role
    """
    async def _dep(
        token: str = Depends(_oauth2_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> str:
        user = await _authenticate(token, db)
        if _ROLE_RANK.get(user.role, 0) < _ROLE_RANK.get(minimum_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required",
            )
        return user.username

    # Give the inner function a unique name so FastAPI's dependency cache
    # treats each require_role(...) call as a distinct dependency.
    _dep.__name__ = f"require_{minimum_role}"
    return _dep


# Pre-built dependency callables — pass to Depends(...)
require_viewer = require_role("viewer")    # any authenticated user
require_operator = require_role("operator")
require_admin = require_role("admin")

# Backward-compatible alias
get_current_user = require_viewer
