"""
auth/router.py
==============
Assembles the FastAPIUsers instance and exposes auth + user management routers.

Routers registered here (to be included in main.py)
----------------------------------------------------
auth_router      : POST /auth/jwt/login, POST /auth/jwt/logout
register_router  : POST /auth/register
reset_router     : POST /auth/forgot-password, POST /auth/reset-password
verify_router    : POST /auth/request-verify-token, POST /auth/verify
users_router     : GET/PATCH /users/me, admin CRUD for superusers

Import into main.py
-------------------
    from auth.router import (
        auth_router, register_router, reset_router,
        verify_router, users_router,
    )
    app.include_router(auth_router,     prefix="/auth/jwt",    tags=["Auth"])
    app.include_router(register_router, prefix="/auth",        tags=["Auth"])
    app.include_router(reset_router,    prefix="/auth",        tags=["Auth"])
    app.include_router(verify_router,   prefix="/auth",        tags=["Auth"])
    app.include_router(users_router,    prefix="/users",       tags=["Users"])
"""

from __future__ import annotations

import uuid

from fastapi_users import FastAPIUsers

from auth.backend import auth_backend
from auth.manager import get_user_manager
from auth.schemas import UserCreate, UserRead, UserUpdate
from db.models.user import User


# ── Core fastapi-users instance ───────────────────────────────────────────────

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# ── Individual routers (mounted in main.py) ───────────────────────────────────

auth_router = fastapi_users.get_auth_router(auth_backend)
"""JWT login / logout endpoints."""

register_router = fastapi_users.get_register_router(UserRead, UserCreate)
"""User registration endpoint."""

reset_router = fastapi_users.get_reset_password_router()
"""Forgot-password and reset-password endpoints."""

verify_router = fastapi_users.get_verify_router(UserRead)
"""Email verification request and confirmation endpoints."""

users_router = fastapi_users.get_users_router(UserRead, UserUpdate)
"""GET/PATCH /me and superuser admin CRUD routes."""
