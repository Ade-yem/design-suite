"""
auth/db.py
==========
SQLAlchemy adapter bridge for fastapi-users.

Provides ``get_user_db`` — a FastAPI dependency that yields the
``SQLAlchemyUserDatabase`` adapter used by ``UserManager`` to read/write
User rows.

This module is kept separate from manager.py to avoid circular imports.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.session import get_async_session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """
    FastAPI dependency yielding the SQLAlchemy user database adapter.

    Parameters
    ----------
    session : AsyncSession
        Injected async database session.

    Yields
    ------
    SQLAlchemyUserDatabase
        Configured database adapter for the User model.
    """
    yield SQLAlchemyUserDatabase(session, User)
