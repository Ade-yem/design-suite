"""
middleware/rate_limit.py
========================
Per-client request rate limiting built on `slowapi`.

A single shared :data:`limiter` is imported by ``main.py`` (to register the
middleware + 429 handler) and by routers (to decorate heavy endpoints such as
file upload, analysis, design and pipeline resume).

Keying
------
Requests are bucketed by the authenticated caller when identifiable, else by
client IP:

1. ``request.state.user`` id, if an upstream dependency placed it there;
2. otherwise the bearer token (hashed) — a stable per-session proxy for a user
   without having to decode the JWT here;
3. otherwise the remote address.

The limiter is disabled in the test environment so the existing suite (which
hammers endpoints via ``TestClient``) is unaffected.
"""

from __future__ import annotations

import hashlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from config import settings


def client_key(request: Request) -> str:
    """Return a stable rate-limit bucket key for the request."""
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is not None:
        return f"user:{user_id}"

    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        return "token:" + hashlib.sha256(token.encode()).hexdigest()[:32]

    return f"ip:{get_remote_address(request)}"


# Disabled under tests so TestClient-driven suites are not throttled.
_ENABLED = settings.APP_ENV not in ("test",)

# ``headers_enabled`` is left off: with it on, slowapi requires every decorated
# endpoint to expose a ``response: Response`` parameter for header injection.
# The endpoints here don't, and limits are still enforced (429) without it.
limiter = Limiter(
    key_func=client_key,
    enabled=_ENABLED,
    default_limits=[],
)
