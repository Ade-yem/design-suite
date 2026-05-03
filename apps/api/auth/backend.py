"""
auth/backend.py
===============
fastapi-users authentication backend: JWT via Bearer token.

Configures the transport (Authorization header), strategy (JWT), and
assembles the ``AuthenticationBackend`` instance used across the app.

Strategy
--------
- Transport  : BearerTransport  (Authorization: Bearer <token>)
- Strategy   : JWTStrategy      (HS256, configurable TTL from settings)

The token payload conforms to the fastapi-users standard:
  {"sub": "<user_id>", "aud": ["fastapi-users:auth"]}
"""

from __future__ import annotations

from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

from config import settings

# Transport: token is sent in the Authorization header as "Bearer <token>".
bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    """
    Build the JWT strategy from application settings.

    Returns
    -------
    JWTStrategy
        Configured JWT strategy with secret and lifetime from settings.
    """
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.JWT_LIFETIME_SECONDS,
    )


# Single named authentication backend; the name is used in token audience
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
