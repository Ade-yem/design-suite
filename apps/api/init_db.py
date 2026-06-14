#!/usr/bin/env python
"""
init_db.py
==========
Production-grade database initialization script for the Structural Design Copilot API.
Connects to the database resolved by configuration and creates all registered tables
(Organisations, Users, OAuthAccounts, Projects, Geometry, etc.) if they do not exist.

Usage
-----
    python init_db.py
"""

import asyncio
import sys
import logging
from typing import Sequence

# Add current folder to path if necessary
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.base import Base
import db.models  # Ensures all ORM models are imported and registered on Base.metadata
from db.session import _get_engine
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("init_db")


async def init_database() -> None:
    """
    Establish connection to the async database engine, create all missing
    tables registered under the declarative Base.metadata, and initialize
    LangGraph checkpointer tables if using a Postgres backend.
    """
    logger.info("Initializing database schemas...")
    
    if not settings.DATABASE_URL:
        logger.error("DATABASE_URL is not configured in settings or .env file.")
        sys.exit(1)
        
    engine = _get_engine()
    
    try:
        # 1. Initialize SQLAlchemy ORM tables
        async with engine.begin() as conn:
            logger.info("Database connection established successfully.")
            
            # Retrieve currently registered table names
            registered_tables: Sequence[str] = list(Base.metadata.tables.keys())
            logger.info("Discovered registered ORM tables: %s", ", ".join(registered_tables))
            
            # Execute schema creation asynchronously inside a transaction block
            logger.info("Executing Base.metadata.create_all() synchronized query...")
            await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database tables initialized/synchronized successfully.")
            
        # 2. Initialize LangGraph checkpoints tables
        if settings.PROJECT_STORE_BACKEND == "postgres":
            logger.info("Initializing LangGraph checkpointer tables...")
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row
            
            async with AsyncConnectionPool(
                conninfo=settings.DATABASE_URL,
                min_size=1,
                max_size=2,
                open=True,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
            ) as pool:
                # pyrefly: ignore [bad-argument-type]
                postgres_saver = AsyncPostgresSaver(pool)
                await postgres_saver.setup()
            logger.info("LangGraph checkpointer tables initialized successfully.")
            
    except Exception as e:
        logger.exception("An error occurred during database table initialization: %s", str(e))
        sys.exit(1)
    finally:
        # Dispose of engine connection pool resources safely
        await engine.dispose()
        logger.info("Database engine resources disposed safely.")


if __name__ == "__main__":
    try:
        asyncio.run(init_database())
    except KeyboardInterrupt:
        logger.warning("Database initialization aborted by user.")
        sys.exit(1)
