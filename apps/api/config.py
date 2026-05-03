"""
config.py
=========
Environment variables and application-wide constants for the Structural Design Copilot API.

All configurable values are read from environment variables (via python-dotenv) with
safe defaults so the application can start without a .env file in development.

Usage
-----
    from config import settings
    print(settings.UPLOAD_DIR)
"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration object.  Values are resolved in this order:
    1. Environment variable
    2. .env file
    3. Default specified here

    Attributes
    ----------
    APP_ENV : str
        Deployment environment. One of ``development`` | ``staging`` | ``production``.
    SECRET_KEY : str
        HMAC secret for JWT signing (fastapi-users).
    JWT_LIFETIME_SECONDS : int
        JWT token validity duration in seconds.
    ALLOWED_ORIGINS : str
        CORS allowed origins. Comma-separated string in env, parsed into a list.
    UPLOAD_DIR : Path
        Filesystem directory where uploaded DXF/PDF files are stored (dev only).
    MAX_UPLOAD_SIZE_MB : int
        Hard limit on uploaded file size in megabytes.
    FILE_STORAGE_BACKEND : str
        File storage implementation to use. One of ``local`` | ``cloudinary``.
        Defaults to ``local``. Set to ``cloudinary`` for production.
    JOB_STORE_TTL_SECONDS : int
        How long job entries are retained in Redis (seconds).
    JOB_STORE_BACKEND : str
        Job store implementation to use. One of ``memory`` | ``redis``.
    PROJECT_STORE_BACKEND : str
        Project store implementation to use. One of ``memory`` | ``postgres``.
    DATABASE_URL : str | None
        Async PostgreSQL DSN (e.g. ``postgresql+asyncpg://user:pw@host/db``).
        Required when PROJECT_STORE_BACKEND is ``postgres``.
    REDIS_URL : str | None
        Redis connection URL. Required when JOB_STORE_BACKEND is ``redis``.
    CLOUDINARY_CLOUD_NAME : str
        Cloudinary cloud name. Required when FILE_STORAGE_BACKEND is ``cloudinary``.
    CLOUDINARY_API_KEY : str
        Cloudinary API key.
    CLOUDINARY_API_SECRET : str
        Cloudinary API secret.
    LOG_LEVEL : str
        Root logging level (DEBUG | INFO | WARNING | ERROR).
    API_VERSION : str
        Semantic version string embedded in OpenAPI metadata.
    GEMINI_API_KEY : str
        Google Gemini API key for AI agent calls.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    JWT_LIFETIME_SECONDS: int = 3600

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── File storage ──────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = Path("uploads")
    MAX_UPLOAD_SIZE_MB: int = 50
    FILE_STORAGE_BACKEND: str = "local"   # "local" | "cloudinary"

    # ── Cloudinary (production file storage) ──────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # ── Job store ─────────────────────────────────────────────────────────────
    JOB_STORE_TTL_SECONDS: int = 3600
    JOB_STORE_BACKEND: str = "memory"    # "memory" | "redis"
    REDIS_URL: str | None = None

    # ── Project / Data store ──────────────────────────────────────────────────
    PROJECT_STORE_BACKEND: str = "memory" # "memory" | "postgres"
    DATABASE_URL: str | None = None

    # ── Logging & meta ────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    API_VERSION: str = "1.0.0"
    GEMINI_API_KEY: str = ""

    # ── Derived properties ────────────────────────────────────────────────────
    @property
    def origins_list(self) -> list[str]:
        """Return ALLOWED_ORIGINS parsed into a Python list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        """Return maximum allowed upload size in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        """Return True when running in production mode."""
        return self.APP_ENV == "production"


settings = Settings()

# Ensure upload directory exists at import time
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── Accepted MIME types for file upload ───────────────────────────────────────
ACCEPTED_MIME_TYPES: set[str] = {
    "image/vnd.dxf",
    "application/dxf",
    "application/acad",
    "application/x-acad",
    "application/autocad_dwg",
    "application/pdf",
    "application/x-pdf",
    # Some browsers send generic octet-stream for DXF
    "application/octet-stream",
}

ACCEPTED_EXTENSIONS: set[str] = {".dxf", ".pdf"}

# ─── Error code registry ───────────────────────────────────────────────────────
ERROR_CODES: dict[str, str] = {
    "GATE_NOT_PASSED":    "Pipeline stage not completed — upstream gate must be confirmed first.",
    "MEMBER_NOT_FOUND":   "Member ID does not exist in this project.",
    "PROJECT_NOT_FOUND":  "Project ID does not exist.",
    "INVALID_LOAD_INPUT": "Load definition failed schema validation.",
    "ANALYSIS_FAILED":    "Analysis engine returned an error for one or more members.",
    "DESIGN_FAILED":      "Design suite returned a failure for one or more members.",
    "FILE_PARSE_ERROR":   "DXF/PDF file could not be parsed.",
    "UNIT_CONFLICT":      "Inconsistent units detected in the input file.",
    "CONVERGENCE_FAILED": "Self-weight iteration did not converge within the iteration limit.",
    "REPORT_NOT_READY":   "Design must be complete before report generation can begin.",
    "JOB_NOT_FOUND":      "Job ID does not exist.",
    "UNSUPPORTED_FILE":   "File type not supported — only DXF and PDF are accepted.",
    "FILE_TOO_LARGE":     f"File exceeds {50} MB limit.",
}
