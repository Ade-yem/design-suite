"""
main.py
=======
Application entry point for the Structural Design Copilot API.

Responsibilities
----------------
- Creates the FastAPI application instance with OpenAPI metadata.
- Configures CORS middleware to allow the React IDE frontend origin.
- Attaches the request logger middleware for per-call timing.
- Registers global error handlers (standardised StructuralAPIError envelope).
- Mounts all domain routers under ``/api/v1/``.
- Exposes ``/health`` for container orchestration liveness probes.

Architecture contract
---------------------
This file contains **no business logic and no calculations**.
All responsibilities are delegated to routers → services → core modules.

Startup
-------
    uvicorn main:app --reload --port 5000
"""

from __future__ import annotations
from typing import AsyncGenerator

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from middleware.error_handler import register_error_handlers
from middleware.request_logger import RequestLoggerMiddleware
from middleware.rate_limit import limiter

# ── Router imports ─────────────────────────────────────────────────────────────
from routers import (
    analysis,
    artifacts,
    design,
    drawings,
    files,
    greeting,
    jobs,
    loading,
    pipeline,
    projects,
    reports,
)
import websocket

# ── Auth routers (fastapi-users) ───────────────────────────────────────────────
from auth.router import (
    auth_router,
    register_router,
    reset_router,
    verify_router,
    users_router,
    google_oauth_router,
    google_callback_router,
)


# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

_log = logging.getLogger(__name__)

# ── LangGraph Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    """
    Manage the application lifecycle.

    Wires a PostgreSaver-backed LangGraph checkpointer using psycopg_pool's
    AsyncConnectionPool when DATABASE_URL is set and PROJECT_STORE_BACKEND
    is postgres. Using a connection pool ensures idle connections are recycled
    and re-established automatically to prevent OperationalErrors.
    Falls back to the default MemorySaver if Postgres is unavailable.

    Parameters
    ----------
    fastapi_app : FastAPI
        The FastAPI application instance.

    Yields
    ------
    None
    """
    import agents.graph as _agent_graph

    _pool = None

    if settings.PROJECT_STORE_BACKEND == "postgres" and settings.DATABASE_URL:
        try:
            from typing import Any
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row

            _log.info("Initializing LangGraph checkpointer with AsyncConnectionPool...")
            _pool: Any = AsyncConnectionPool(
                conninfo=settings.DATABASE_URL,
                min_size=1,
                max_size=10,
                open=False,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
            )
            await _pool.open()

            _postgres_saver = AsyncPostgresSaver(_pool)
            await _postgres_saver.setup()
            _agent_graph.app = _agent_graph.build_app(_postgres_saver)
            _log.info("LangGraph checkpointer: AsyncPostgresSaver with AsyncConnectionPool (postgres).")
        except Exception as exc:  # package not installed or DB not reachable
            if settings.APP_ENV not in ("development", "test"):
                _log.critical("Failed to initialize Postgres checkpointer in production: %s", exc)
                raise exc
            _log.warning("LangGraph PostgreSaver with AsyncConnectionPool unavailable (%s) — falling back to MemorySaver.", exc)
            _pool = None

    yield  # ── application runs ──────────────────────────────────────────────

    if _pool is not None:
        try:
            await _pool.close()
            _log.info("Successfully closed LangGraph checkpointer AsyncConnectionPool.")
        except Exception as exc:
            _log.error("Failed to cleanly close Postgres checkpointer connection pool: %s", exc)

# ── Application ────────────────────────────────────────────────────────────────
app = FastAPI(
    lifespan=lifespan,
    title="StructAI Copilot API",
    version=settings.API_VERSION,
    description=(
        "AI-driven multi-agent structural engineering backend. "
        "Exposes the full loading → analysis → design → reporting pipeline "
        "as versioned REST endpoints with enforced stage-gate sequencing."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Middleware stack ───────────────────────────────────────────────────────────
# Note: middleware is executed in LIFO (last-added = outermost).

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggerMiddleware)

# ── Rate limiting (slowapi) ─────────────────────────────────────────────────────
# Per-client throttling on heavy endpoints (upload / analysis / design / resume).
# Disabled under APP_ENV=test (see middleware.rate_limit).
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Error handlers ─────────────────────────────────────────────────────────────
register_error_handlers(app)

# ── Routers ────────────────────────────────────────────────────────────────────
# v1 domain routers
app.include_router(greeting.router,  prefix="/api/v1/greeting",  tags=["Greeting"])
app.include_router(projects.router,  prefix="/api/v1/projects",  tags=["Projects"])
app.include_router(files.router,     prefix="/api/v1/files",     tags=["Files"])
app.include_router(loading.router,   prefix="/api/v1/loading",   tags=["Loading"])
app.include_router(analysis.router,  prefix="/api/v1/analysis",  tags=["Analysis"])
app.include_router(design.router,    prefix="/api/v1/design",    tags=["Design"])
app.include_router(drawings.router,  prefix="/api/v1/drawings",  tags=["Drawings"])
app.include_router(reports.router,   prefix="/api/v1/reports",   tags=["Reports"])
app.include_router(pipeline.router,  prefix="/api/v1/pipeline",  tags=["Pipeline"])
app.include_router(jobs.router,      prefix="/api/v1/jobs",      tags=["Jobs"])
app.include_router(artifacts.router, prefix="/api/v1/artifacts", tags=["Artifacts"])

# ── Auth routes (fastapi-users) ────────────────────────────────────────────────
app.include_router(auth_router,          prefix="/api/auth/jwt",    tags=["Auth"])
app.include_router(register_router,      prefix="/api/auth",        tags=["Auth"])
app.include_router(reset_router,         prefix="/api/auth",        tags=["Auth"])
app.include_router(verify_router,        prefix="/api/auth",        tags=["Auth"])
app.include_router(users_router,         prefix="/api/users",       tags=["Users"])
# google_callback_router must be mounted first — FastAPI uses first-match-wins,
# so this custom redirect handler takes precedence over the default JSON response
# from google_oauth_router's /callback route.
app.include_router(google_callback_router, prefix="/api/auth/google", tags=["Auth"])
app.include_router(google_oauth_router,    prefix="/api/auth/google", tags=["Auth"])

# WebSockets
app.include_router(websocket.router, tags=["WebSockets"])


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """
    Liveness probe endpoint for container orchestration.

    Returns
    -------
    dict
        ``{status: "ok", version: "1.0.0", environment: "development"}``
    """
    return {
        "status": "ok",
        "version": settings.API_VERSION,
        "environment": settings.APP_ENV,
    }
