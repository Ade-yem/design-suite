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

# ── Router imports ─────────────────────────────────────────────────────────────
from routers import (
    analysis,
    artifacts,
    chat,
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
    Wire a PostgreSaver-backed LangGraph checkpointer when DATABASE_URL is set.
    Falls back to the default MemorySaver (already compiled in agents.graph) if
    Postgres is unavailable or the package is not installed.
    """
    import agents.graph as _agent_graph

    _postgres_saver_ctx = None

    if settings.PROJECT_STORE_BACKEND == "postgres" and settings.DATABASE_URL:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            # Keep reference to the context manager
            _postgres_saver_ctx = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
            _postgres_saver = await _postgres_saver_ctx.__aenter__()
            await _postgres_saver.setup()
            _agent_graph.app = _agent_graph.build_app(_postgres_saver)
            _log.info("LangGraph checkpointer: AsyncPostgresSaver (postgres).")
        except Exception as exc:  # package not installed or DB not reachable
            if settings.APP_ENV not in ("development", "test"):
                _log.critical("Failed to initialize Postgres checkpointer in production: %s", exc)
                raise exc
            _log.warning("LangGraph PostgreSaver unavailable (%s) — falling back to MemorySaver.", exc)
            _postgres_saver_ctx = None

    yield  # ── application runs ──────────────────────────────────────────────

    if _postgres_saver_ctx is not None:
        try:
            # Await the context manager exit
            await _postgres_saver_ctx.__aexit__(None, None, None)
        except Exception as exc:
            _log.error("Failed to cleanly exit Postgres checkpointer context manager: %s", exc)

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
