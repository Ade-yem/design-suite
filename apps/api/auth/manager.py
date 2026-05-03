"""
auth/manager.py
===============
fastapi-users UserManager — custom hooks for registration, verification,
password reset, and request-scoped user fetching.

The ``UserManager`` is the central place to add application logic tied to
auth lifecycle events (e.g. creating an org on first registration, sending
welcome emails, audit logging).

Dependencies (install)
----------------------
    pip install fastapi-users[sqlalchemy] fastapi-mail  (optional for email)
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

from auth.auth_db import get_user_db
from config import settings

logger = logging.getLogger(__name__)

SECRET = settings.SECRET_KEY


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    Application-level user manager.

    Extends fastapi-users ``BaseUserManager`` with project-specific hooks.

    Attributes
    ----------
    reset_password_token_secret : str
        Secret used to sign password reset tokens.
    verification_token_secret : str
        Secret used to sign email verification tokens.
    """

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None) -> None:
        """
        Called after a successful registration.

        Hook point for: sending a welcome email, creating a default organisation,
        or audit logging.

        Parameters
        ----------
        user : User
            Newly registered user.
        request : Request | None
            Originating HTTP request (may be None in tests).
        """
        logger.info("User %s registered (email: %s).", user.id, user.email)
        # TODO: create default Organisation if user.organisation_id is None
        # TODO: send welcome email via fastapi-mail

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        """
        Called after a password reset is requested.

        Parameters
        ----------
        user : User
            User who requested the reset.
        token : str
            Signed reset token (send via email link).
        request : Request | None
            Originating HTTP request.
        """
        logger.info("User %s requested password reset.", user.email)
        # TODO: send reset email with token embedded in link

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        """
        Called after an email verification is requested.

        Parameters
        ----------
        user : User
            User requesting verification.
        token : str
            Signed verification token (send via email link).
        request : Request | None
            Originating HTTP request.
        """
        logger.info("Verification requested for user %s.", user.email)
        # TODO: send verification email with token embedded in link


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> UserManager:
    """
    FastAPI dependency that yields a UserManager instance.

    Parameters
    ----------
    user_db : SQLAlchemyUserDatabase
        Injected database adapter for the User model.

    Yields
    ------
    UserManager
        Configured user manager instance.
    """
    yield UserManager(user_db)
