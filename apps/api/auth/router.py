# pyrefly: ignore [bad-argument-type, missing-attribute]

"""
auth/router.py
==============
Assembles the Custom Authentication Routers and exposes user management routes.

Overrides the standard fastapi-users login endpoints to introduce:
1. **Email Verification Gate**: Rejects unverified login attempts.
2. **Stateful Email-Based 2FA**: Generates a 6-digit OTP code on credentials matching,
   commits it to the database with a 5-minute expiry, sends it via Resend,
   and challenges the user rather than issuing the token immediately.
3. **Google OAuth Federated Router**: Mounts the Google social authentication pipeline.
"""

from __future__ import annotations

import logging
import uuid
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import JWTStrategy
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from pydantic import BaseModel, Field

from auth.backend import auth_backend
from auth.manager import UserManager, get_user_manager
from auth.schemas import UserCreate, UserRead, UserUpdate
from db.models.user import User
from config import settings
from services.email import email_service

logger = logging.getLogger(__name__)

# ── Core fastapi-users instance ───────────────────────────────────────────────

fastapi_users = FastAPIUsers[User, uuid.UUID](
    # pyrefly: ignore [bad-argument-type]
    get_user_manager,
    # pyrefly: ignore [bad-argument-type]
    [auth_backend],
)

# ── Custom Authentication Router with 2FA / Verification Gates ────────────────

auth_router = APIRouter()


class TwoFactorVerifyRequest(BaseModel):
    """
    Request payload schema for two-factor verification.
    """

    user_id: uuid.UUID = Field(..., description="Unique User identifier.")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code.")


@auth_router.post("/login")
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(auth_backend.get_strategy),
) -> Any:
    """
    Stateful login endpoint incorporating verification and 2FA gates.

    1. Validates username and password.
    2. Enforces the email verification constraint (is_verified = True).
    3. Triggers email 2FA if enabled on the user profile.
    4. Generates standard JWT token if 2FA is disabled.

    Parameters
    ----------
    request : Request
        FastAPI Request context.
    credentials : OAuth2PasswordRequestForm
        Login credentials form (username, password).
    user_manager : UserManager
        Injected user lifecycle manager.
    strategy : JWTStrategy
        Injected JWT signing strategy.

    Returns
    -------
    dict | Response
        2FA redirect challenge payload OR standard JWT token response.

    Raises
    ------
    HTTPException
        For invalid credentials, unverified accounts, or inactive users.
    """
    # 1. Authenticate user credentials
    user = await user_manager.authenticate(credentials)
    if user is None or not user.is_active: # pyrefly: ignore [missing-attribute]
        logger.warning("Failed login attempt for email: %s", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )

    # 2. Gate 1: Check Email Verification
    if not user.is_verified: # pyrefly: ignore [missing-attribute]
        # pyrefly: ignore [missing-attribute]
        logger.info("Enforcing verification gate: Blocked unverified user login for %s", user.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EMAIL_NOT_VERIFIED",
        )

    # 3. Gate 2: Stateful Two-Factor Authentication
    if user.is_2fa_enabled: # pyrefly: ignore [missing-attribute]
        code = f"{random.randint(100000, 999999)}"
        # Set expiry to 5 minutes from now in UTC
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        user.two_factor_code = code # pyrefly: ignore [missing-attribute]
        user.two_factor_expires_at = expires_at # pyrefly: ignore [missing-attribute]

        # Save active OTP code state to database
        # pyrefly: ignore [missing-attribute]
        user_manager.user_db.session.add(user)
        # pyrefly: ignore [missing-attribute]
        await user_manager.user_db.session.commit()

        logger.info("Dispatched 2FA PIN challenge code to user %s.", user.email) # pyrefly: ignore [missing-attribute]
        await email_service.send_2fa_code_email(user.email, code) # pyrefly: ignore [missing-attribute]

        return {
            "status": "two_factor_required",
            "user_id": str(user.id), # pyrefly: ignore [missing-attribute]
            "email": user.email, # pyrefly: ignore [missing-attribute]
        }

    # 4. Standard Login execution
    response = await auth_backend.login(strategy, user)
    await user_manager.on_after_login(user, request, response)
    return response


@auth_router.post("/two-factor-verify")
async def two_factor_verify(
    request: Request,
    verify_data: TwoFactorVerifyRequest,
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(auth_backend.get_strategy),
) -> Any:
    """
    Verify a stateful 2FA OTP pin code and return the final JWT Bearer Token.

    Parameters
    ----------
    request : Request
        FastAPI Request context.
    verify_data : TwoFactorVerifyRequest
        OTP pin and User ID.
    user_manager : UserManager
        Injected user manager.
    strategy : JWTStrategy
        Injected JWT signing strategy.

    Returns
    -------
    Response
        Standard JWT token response.

    Raises
    ------
    HTTPException
        If the pin code is incorrect, expired, or the user is not found.
    """
    user = await user_manager.get(verify_data.user_id)
    if not user or not user.is_active: # pyrefly: ignore [missing-attribute]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="USER_NOT_FOUND",
        )

    # Re-enforce verification check
    if not user.is_verified: # pyrefly: ignore [missing-attribute]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EMAIL_NOT_VERIFIED",
        )

    # Validate active code and check for expiration
    expires_at = user.two_factor_expires_at # pyrefly: ignore [missing-attribute]
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if (
        not user.two_factor_code # pyrefly: ignore [missing-attribute]
        or user.two_factor_code != verify_data.code
        or expires_at is None
        or datetime.now(timezone.utc) > expires_at
    ):
        # pyrefly: ignore [missing-attribute]
        logger.warning("Rejected invalid or expired 2FA code for user %s.", user.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_OR_EXPIRED_CODE",
        )

    # Clear OTP state upon successful verification to prevent code reuse (replay protection)
    user.two_factor_code = None # pyrefly: ignore [missing-attribute]
    user.two_factor_expires_at = None # pyrefly: ignore [missing-attribute]
    # pyrefly: ignore [missing-attribute]
    user_manager.user_db.session.add(user)
    # pyrefly: ignore [missing-attribute]
    await user_manager.user_db.session.commit()

    # Authenticate and issue JWT token
    response = await auth_backend.login(strategy, user)
    await user_manager.on_after_login(user, request, response)
    return response


@auth_router.post("/logout")
async def logout(
    request: Request,
    strategy: JWTStrategy = Depends(auth_backend.get_strategy),
    user_token: tuple[User, str] = Depends(
        fastapi_users.authenticator.current_user_token(active=True)
    ),
) -> Any:
    """
    Stateless logout endpoint.

    Parameters
    ----------
    request : Request
        FastAPI Request context.
    strategy : JWTStrategy
        Injected JWT signing strategy.
    user_token : tuple[User, str]
        Tuple containing the active User and their active token string.

    Returns
    -------
    Response
        Standard fastapi-users logout response (HTTP 204).
    """
    user, token = user_token
    # pyrefly: ignore [bad-argument-type]
    response = await auth_backend.logout(strategy, user, token)
    return response


# ── Individual routers (mounted in main.py) ───────────────────────────────────

register_router = fastapi_users.get_register_router(UserRead, UserCreate)
"""User registration endpoint."""

reset_router = fastapi_users.get_reset_password_router()
"""Forgot-password and reset-password endpoints."""

verify_router = fastapi_users.get_verify_router(UserRead)
"""Email verification request and confirmation endpoints."""

users_router = fastapi_users.get_users_router(UserRead, UserUpdate)
"""GET/PATCH /me and superuser admin CRUD routes."""

# ── Google OAuth client and router configuration ──────────────────────────────

google_client = GoogleOAuth2(
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET
)

if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
    logger.warning(
        "Google OAuth is missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET"
    )

google_oauth_router = fastapi_users.get_oauth_router(
    google_client,
    # pyrefly: ignore [bad-argument-type]
    auth_backend,
    settings.SECRET_KEY,
    associate_by_email=True,
    is_verified_by_default=True,
    redirect_url=f"{settings.APP_URL}/api/auth/google/callback"
)
"""Google OAuth Authorization and callback endpoints router."""

# ── Custom Google callback that redirects to the frontend ─────────────────────
# fastapi-users' default OAuth callback returns a raw JSON token response, which
# leaves the user staring at raw JSON in the browser. This override intercepts
# the callback, issues the JWT, and redirects to the frontend /auth/callback page.

_google_callback_dep = OAuth2AuthorizeCallback(
    google_client,
    redirect_url=f"{settings.APP_URL}/api/auth/google/callback",
)

google_callback_router = APIRouter()


@google_callback_router.get("/callback")
async def google_oauth_callback(
    request: Request,
    access_token_state: tuple = Depends(_google_callback_dep),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(auth_backend.get_strategy),
) -> RedirectResponse:
    oauth_token, _ = access_token_state
    account_id, account_email = await google_client.get_id_email(oauth_token["access_token"])

    try:
        # pyrefly: ignore [bad-argument-type]
        user = await user_manager.oauth_callback(
            "google",
            oauth_token["access_token"],
            account_id,
            # pyrefly: ignore [bad-argument-type]
            account_email,
            oauth_token.get("expires_at"),
            oauth_token.get("refresh_token"),
            request,
            associate_by_email=True,
            is_verified_by_default=True,
        )
    except Exception:
        logger.exception("OAuth callback failed for account %s", account_email)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=oauth_failed",
            status_code=302,
        )

    if not user.is_active:  # pyrefly: ignore [missing-attribute]
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=account_inactive",
            status_code=302,
        )

    # pyrefly: ignore [bad-argument-type]
    jwt = await strategy.write_token(user)
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/callback?token={jwt}",
        status_code=302,
    )
