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
import httpx

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

class GoogleProfileResponse(BaseModel):
    """
    Response schema for google profile.
    """
    fullname: str | None = Field(..., description="User's full name.")
    email: str | None = Field(..., description="Email.")
    image: str | None = Field(..., description="User's image.")


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


async def fetch_google_profile(access_token: str) -> GoogleProfileResponse | None:
    """
    Fetch user profile data from Google People API and transform it.
    
    Returns:
        A dictionary matching {fullname: str, email: str, image: str} or None if the request fails.
    """
    url = "https://people.googleapis.com/v1/people/me"
    # Request names, emailAddresses, and photos in a single API call
    params = {"personFields": "names,emailAddresses,photos"}
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Extract names safely
                names = data.get("names", [])
                fullname = names[0].get("displayName") if names else None
                
                # Extract email address safely
                emails = data.get("emailAddresses", [])
                email = emails[0].get("value") if emails else None
                
                # Extract profile image safely
                photos = data.get("photos", [])
                image = photos[0].get("url") if photos else None
                
                # Transform to target schema
                return GoogleProfileResponse(fullname=fullname, email=email, image=image)
                
            logger.error("Google API responded with status %d: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Failed to fetch profile from Google People API: %s", str(e))
        
    return None


@google_callback_router.get("/callback")
async def google_oauth_callback(
    request: Request,
    access_token_state: tuple = Depends(_google_callback_dep),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(auth_backend.get_strategy),
) -> RedirectResponse:
    from db.models.organisation import Organisation

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

    # 1. Fetch displayName and image from Google People API
    profile_data = await fetch_google_profile(oauth_token["access_token"])
    # pyrefly: ignore [missing-attribute]
    session = user_manager.user_db.session

    needs_commit = False
    if profile_data:
        # pyrefly: ignore [missing-attribute]
        if profile_data.fullname and not user.full_name:
            # pyrefly: ignore [missing-attribute]
            user.full_name = profile_data.fullname
            needs_commit = True
        # pyrefly: ignore [missing-attribute]
        if profile_data.image and not user.image:
            # pyrefly: ignore [missing-attribute]
            user.image = profile_data.image
            needs_commit = True

    # 2. Automatically create default Organisation if OAuth user has no tenant ID
    # pyrefly: ignore [missing-attribute]
    if user.organisation_id is None:
        # pyrefly: ignore [missing-attribute]
        base_name = user.full_name or user.email.split("@")[0]
        org_name = f"{base_name.title()}'s Organisation"
        try:
            unique_slug = await user_manager._generate_unique_slug(session, base_name)
            org = Organisation(name=org_name, slug=unique_slug)
            session.add(org)
            await session.flush()  # Generates org ID
            
            # pyrefly: ignore [missing-attribute]
            user.organisation_id = org.id
            session.add(user)
            needs_commit = True
            logger.info(
                "Automatically created default Organisation '%s' (slug: %s) for OAuth user %s",
                org_name,
                unique_slug,
                # pyrefly: ignore [missing-attribute]
                user.email,
            )
        except Exception as e:
            logger.error(
                "Failed to auto-create Organisation for OAuth user %s: %s",
                # pyrefly: ignore [missing-attribute]
                user.email,
                str(e),
                exc_info=True,
            )
            await session.rollback()
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/login?error=organisation_creation_failed",
                status_code=302,
            )

    if needs_commit:
        await session.commit()

    # pyrefly: ignore [bad-argument-type]
    jwt = await strategy.write_token(user)
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/callback?token={jwt}",
        status_code=302,
    )

