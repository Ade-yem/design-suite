import asyncio
from logging.config import fileConfig

import sys
import os
import re

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from db.base import Base
import db.models  # Ensures all ORM models are registered on Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_db_url_and_args() -> tuple[str, dict]:
    """
    Read the DATABASE_URL from settings, map the scheme to asyncpg,
    strip unsupported parameters, and configure ssl connect_args.
    """
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in settings or .env file.")
    
    # 1. Map postgresql: to postgresql+asyncpg:
    db_url = re.sub(r'^postgresql:', 'postgresql+asyncpg:', settings.DATABASE_URL)
    
    # 2. Strip unsupported C-library parameters (sslmode, channel_binding)
    if "?" in db_url:
        base_url, query_str = db_url.split("?", 1)
        unsupported_params = ["sslmode", "channel_binding"]
        params = []
        for param in query_str.split("&"):
            if not any(param.startswith(unsupported + "=") for unsupported in unsupported_params):
                params.append(param)
        db_url = f"{base_url}?{'&'.join(params)}" if params else base_url
        
    connect_args = {}
    if "sslmode" in settings.DATABASE_URL or "ssl=require" in settings.DATABASE_URL:
        connect_args["ssl"] = True
        
    return db_url, connect_args


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url, _ = get_db_url_and_args()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    url, connect_args = get_db_url_and_args()
    
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
