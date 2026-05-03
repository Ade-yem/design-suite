"""
auth/dependencies.py
====================
Re-exports fastapi-users current-user dependencies for use across all routers.

This module is the single import point for auth guards. Routers should
``Depends(current_active_user)`` rather than importing from fastapi_users directly,
so the dependency can be swapped or mocked in tests.

Exported dependencies
---------------------
current_active_user
    Returns the authenticated User or raises 401.
current_superuser
    Returns the authenticated User only if is_superuser=True, else 403.
optional_current_user
    Returns the authenticated User or None (for public-but-personalised endpoints).

Usage (in a router)
-------------------
    from auth.dependencies import current_active_user
    from db.models.user import User

    @router.get("/me")
    async def me(user: User = Depends(current_active_user)):
        return user
"""

from __future__ import annotations

from auth.router import fastapi_users

# ── Re-exported guards ────────────────────────────────────────────────────────

current_active_user = fastapi_users.current_user(active=True)
"""Require an active authenticated user. Raises HTTP 401 if not authenticated."""

current_superuser = fastapi_users.current_user(active=True, superuser=True)
"""Require an active superuser. Raises HTTP 403 if not a superuser."""

optional_current_user = fastapi_users.current_user(optional=True)
"""Return the current user or None (no auth required)."""
