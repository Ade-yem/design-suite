"""
script/drop_all_tables.py
=========================
A utility script to drop all tables from the PostgreSQL database (including alembic_version),
resetting the schema completely.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add apps/api to path so imports work correctly
sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.base import Base
from db.session import _get_engine
# Import models to register them on Base.metadata
import db.models
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("drop_all_tables")


async def drop_all_tables():
    logger.info("Connecting to database...")
    engine = _get_engine()
    
    async with engine.begin() as conn:
        logger.info("Dropping all registered application tables...")
        # Run drop_all via run_sync to execute synchronous metadata operations on async connection
        await conn.run_sync(Base.metadata.drop_all)
        
        logger.info("Dropping alembic_version table...")
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
        
    logger.info("All tables dropped successfully!")


if __name__ == "__main__":
    asyncio.run(drop_all_tables())
