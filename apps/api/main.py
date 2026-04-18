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
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from middleware.error_handler import register_error_handlers
from middleware.request_logger import RequestLoggerMiddleware

# ── Router imports ─────────────────────────────────────────────────────────────
from routers import (
    analysis,
    chat,
    design,
    files,
    jobs,
    loading,
    pipeline,
    projects,
    reports,
)

# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

# ── Application ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Structural Design Copilot API",
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
app.include_router(projects.router,  prefix="/api/v1/projects",  tags=["Projects"])
app.include_router(files.router,     prefix="/api/v1/files",     tags=["Files"])
app.include_router(loading.router,   prefix="/api/v1/loading",   tags=["Loading"])
app.include_router(analysis.router,  prefix="/api/v1/analysis",  tags=["Analysis"])
app.include_router(design.router,    prefix="/api/v1/design",    tags=["Design"])
app.include_router(reports.router,   prefix="/api/v1/reports",   tags=["Reports"])
app.include_router(pipeline.router,  prefix="/api/v1/pipeline",  tags=["Pipeline"])
app.include_router(jobs.router,      prefix="/api/v1/jobs",      tags=["Jobs"])

# Legacy routers (kept for backward compatibility with existing frontend)
app.include_router(chat.router, prefix="/api", tags=["Chat (Legacy)"])


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
