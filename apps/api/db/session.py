"""
db/session.py
=============
Async SQLAlchemy engine and session factory.

Provides ``get_async_session`` — a FastAPI dependency that yields a database
session per request and commits/rolls back automatically.

Also exposes ``async_session_maker`` for use outside of a request context
(e.g. startup migrations, background tasks).

Usage (in a router)
-------------------
    from db.session import get_async_session
    from sqlalchemy.ext.asyncio import AsyncSession
    from fastapi import Depends

    async def my_endpoint(db: AsyncSession = Depends(get_async_session)):
        result = await db.execute(select(MyModel))
        ...
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

# Engine is created lazily — only initialised when DATABASE_URL is set.
# In-memory / development mode uses the MemoryStore adapters instead.
_engine = None
_async_session_maker = None


def _get_engine():
    """
    Return (or create) the async SQLAlchemy engine.

    Returns
    -------
    AsyncEngine
        Configured async database engine.

    Raises
    ------
    RuntimeError
        If DATABASE_URL is not set in configuration.
    """
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Set it in your .env file or use the in-memory store backend."
            )
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=(settings.APP_ENV == "development"),
            pool_pre_ping=True,
        )
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """
    Return the async session factory, creating it on first call.

    Returns
    -------
    async_sessionmaker[AsyncSession]
        Configured session factory.
    """
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a scoped async database session.

    The session is committed on success and rolled back on any exception.
    Always closed at the end of the request.

    Yields
    ------
    AsyncSession
        Active database session bound to the current request.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
