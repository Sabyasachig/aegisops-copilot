"""Shared slowapi Limiter instance and key-function helpers.

The limiter is created once at module import time.  The storage backend is
controlled by the ``AIOPS_RATE_LIMIT_STORAGE_URI`` environment variable so
that tests can use ``memory://`` (fast, no Redis needed) while production uses
a Redis URI (``redis://…/3`` by default).

Usage in route modules::

    from ..limiter import limiter, get_user_identifier

    @router.post("/some/endpoint")
    @limiter.limit(lambda req: get_settings().rate_limit_per_user, key_func=get_user_identifier)
    @limiter.limit(lambda req: get_settings().rate_limit_per_ip)
    async def my_endpoint(request: Request, ...):
        ...

Register the limiter on the app in ``create_app()``::

    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from .limiter import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""

from __future__ import annotations

import base64
import json
import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def get_user_identifier(request) -> str:
    """Return ``'user:<username>'`` decoded from the Bearer JWT, or the client IP.

    This is used as the rate-limit key for per-user limiting so that different
    users each have their own independent counter.  If no valid JWT is present
    (unauthenticated requests) the key falls back to the client IP address.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            token = auth.split(" ", 1)[1]
            parts = token.split(".")
            if len(parts) == 3:
                # Decode the JWT payload (no signature verification needed here
                # — we only need the 'sub' claim for the rate-limit key; the
                # actual auth check is handled by the auth dependency).
                padding = "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.b64decode(parts[1] + padding))
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
        except Exception:
            pass
    return get_remote_address(request)


# ---------------------------------------------------------------------------
# Limiter singleton
# ---------------------------------------------------------------------------

# Storage URI is resolved at module import time via os.getenv() so that
# conftest.py can set AIOPS_RATE_LIMIT_STORAGE_URI=memory:// *before* any
# aegisops_api module is imported, ensuring tests never hit Redis.
_storage_uri: str = os.getenv(
    "AIOPS_RATE_LIMIT_STORAGE_URI",
    "redis://localhost:6379/3",
)

limiter = Limiter(
    key_func=get_remote_address,   # default key; routes can override per-decorator
    storage_uri=_storage_uri,
    headers_enabled=True,          # emit X-RateLimit-* and Retry-After headers
)
