"""
auth/manager.py
===============
fastapi-users UserManager — custom hooks for registration, verification,
password reset, and request-scoped user fetching.

The ``UserManager`` is the central place to add application logic tied to
auth lifecycle events:
- Automatically creates a unique multi-tenant Organisation for users upon
  registration if they did not join via an invite.
- Enforces security rules such as restricting password resets to local
  email/password credentials (blocking Google-only OAuth users).
- Dispatches transactional emails asynchronously via the Resend-driven
  ``EmailService``.
"""

from __future__ import annotations

import re
import uuid
import random
import logging
from typing import Optional, Any, cast

from fastapi import Depends, Request, HTTPException, status
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select

from db.models.user import User
from db.models.organisation import Organisation
from auth.auth_db import get_user_db
from config import settings
from services.email import email_service

logger = logging.getLogger(__name__)

SECRET = settings.SECRET_KEY


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    Application-level user manager.

    Extends fastapi-users ``BaseUserManager`` with custom hooks for
    registration, verification, password resets, and multitenant onboarding.

    Attributes
    ----------
    reset_password_token_secret : str
        Secret used to sign password reset tokens.
    verification_token_secret : str
        Secret used to sign email verification tokens.
    """

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    def _slugify(self, text: str) -> str:
        """
        Convert display name or email to a URL-safe lowercase slug.

        Parameters
        ----------
        text : str
            Source string to slugify.

        Returns
        -------
        str
            URL-safe slug.
        """
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "-", text)
        text = re.sub(r"^-+|-+$", "", text)
        return text or "tenant"

    async def _generate_unique_slug(self, session: Any, base_name: str) -> str:
        """
        Generate a unique organisation slug, appending random tokens in case of collision.

        Parameters
        ----------
        session : AsyncSession
            Active database session.
        base_name : str
            Name used as the basis for the slug.

        Returns
        -------
        str
            Guaranteed unique slug.
        """
        base_slug = self._slugify(base_name)
        slug = base_slug
        
        # Attempt to find an unused slug
        for _ in range(10):
            result = await session.execute(
                select(Organisation).where(Organisation.slug == slug)
            )
            existing = result.scalar_one_or_none()
            if not existing:
                return slug
            # Append random 4-digit number to avoid conflict
            slug = f"{base_slug}-{random.randint(1000, 9999)}"

        # Fail-safe absolute unique slug using short UUID
        return f"{base_slug}-{uuid.uuid4().hex[:8]}"

    # pyrefly: ignore [bad-override]
    async def forgot_password(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        """
        Request password reset token.

        Restricts password resets strictly to users who registered with
        email/password. Raises a 400 Bad Request if the user registered
        via social OAuth only.

        Parameters
        ----------
        user : User
            User requesting reset.
        request : Request | None
            Originating HTTP request.

        Raises
        ------
        HTTPException
            If the user is social-only (has no hashed password).
        """
        if not user.hashed_password:
            logger.warning("Rejecting password reset request for OAuth-only user: %s", user.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PASSWORD_RESET_NOT_ALLOWED_OAUTH_ONLY",
            )
        # pyrefly: ignore [bad-argument-type]
        await super().forgot_password(user, request)

    # pyrefly: ignore [bad-override]
    async def on_after_register(self, user: User, request: Optional[Request] = None) -> None:
        """
        Lifecycle hook triggered after a successful registration.

        Generates a tenant Organisation for the user, triggers the welcome
        email, and dispatches the email verification token.

        Parameters
        ----------
        user : User
            Newly registered User record.
        request : Request | None
            Originating HTTP request.
        """
        logger.info("User %s registered (email: %s).", user.id, user.email)
        
        # 1. Automatically create default Organisation if user has no tenant ID
        if user.organisation_id is None:
            base_name = user.full_name or user.email.split("@")[0]
            org_name = f"{base_name.title()}'s Organisation"
            
            user_db = cast(SQLAlchemyUserDatabase, self.user_db)
            session = user_db.session
            try:
                unique_slug = await self._generate_unique_slug(session, base_name)
                org = Organisation(name=org_name, slug=unique_slug)
                session.add(org)
                await session.flush()  # Generates org ID
                
                user.organisation_id = org.id
                session.add(user)
                await session.commit()
                logger.info(
                    "Automatically created default Organisation '%s' (slug: %s) for user %s",
                    org_name,
                    unique_slug,
                    user.email,
                )
            except Exception as e:
                logger.error(
                    "Failed to auto-create Organisation for user %s: %s",
                    user.email,
                    str(e),
                    exc_info=True,
                )
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="ORGANISATION_CREATION_FAILED",
                )

        # 2. Asynchronously dispatch the welcome onboarding email
        await email_service.send_welcome_email(user.email, user.full_name or "there")

        # 3. Automatically request email verification, triggering verification email dispatch
        try:
            # pyrefly: ignore [bad-argument-type]
            await self.request_verify(user, request)
        except Exception as e:
            logger.error(
                "Failed to automatically dispatch email verification for user %s: %s",
                user.email,
                str(e),
            )

    # pyrefly: ignore [bad-override]
    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        """
        Lifecycle hook triggered after a password reset is requested.

        Parameters
        ----------
        user : User
            User who requested the reset.
        token : str
            Signed reset token.
        request : Request | None
            Originating HTTP request.
        """
        logger.info("Dispatching password reset link to user %s.", user.email)
        await email_service.send_reset_password_email(user.email, token)

    # pyrefly: ignore [bad-override]
    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        """
        Lifecycle hook triggered after an email verification is requested.

        Parameters
        ----------
        user : User
            User requesting verification.
        token : str
            Signed verification token.
        request : Request | None
            Originating HTTP request.
        """
        logger.info("Dispatching email verification token link to user %s.", user.email)
        await email_service.send_verification_email(user.email, token)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    """
    FastAPI dependency yielding the UserManager instance.

    Parameters
    ----------
    user_db : SQLAlchemyUserDatabase
        Injected user database adapter.

    Yields
    ------
    UserManager
        Configured user manager.
    """
    yield UserManager(user_db)
