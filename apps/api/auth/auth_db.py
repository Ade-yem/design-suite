"""
auth/auth_db.py
===============
SQLAlchemy adapter bridge for fastapi-users.

Provides ``get_user_db`` — a FastAPI dependency that yields the
``SQLAlchemyUserDatabase`` adapter configured with both the ``User``
and the ``OAuthAccount`` models, allowing users to register, log in,
and associate multiple social identities.

This module is kept separate from manager.py to avoid circular imports.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.models.oauth import OAuthAccount
from db.session import get_async_session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """
    FastAPI dependency yielding the SQLAlchemy user database adapter.

    Binds both the User table and the OAuthAccount table for handling
    federated logins and social account association.

    Parameters
    ----------
    session : AsyncSession
        Injected async database session.

    Yields
    ------
    SQLAlchemyUserDatabase
        Configured database adapter bound to User and OAuthAccount models.
    """
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)
