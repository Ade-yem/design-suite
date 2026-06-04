"""
storage/artifact_store.py
=========================
Pluggable artifact persistence layer.

Supports two backends controlled by ``settings.PROJECT_STORE_BACKEND``:
- ``"memory"``   — in-process dict store (development / testing)
- ``"postgres"`` — async SQLAlchemy store backed by PostgreSQL

The public interface is identical for both backends (all methods are
``async def``) so routers call ``await artifact_store.<method>()`` regardless of
the active backend — mirroring ``storage.project_store``.

Public interface
----------------
create_snapshot(project_id, stage, content, ...)   → ArtifactRecord
list_for_project(project_id)                        → list[ArtifactRecord]
get(artifact_id)                                    → ArtifactRecord | None
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from db.models.artifact import ArtifactStage
from schemas.artifact import ArtifactRecord

logger = logging.getLogger(__name__)


def _serialize_content(content: dict | str) -> str:
    """Serialize a snapshot payload to a JSON string if it is a dict."""
    if isinstance(content, dict):
        return json.dumps(content)
    return content


def _stage_value(stage: ArtifactStage | str) -> str:
    """Normalize an ArtifactStage (or raw string) to its string value."""
    return stage.value if isinstance(stage, ArtifactStage) else str(stage)


# ── In-memory implementation ──────────────────────────────────────────────────


class MemoryArtifactStore:
    """
    In-process in-memory artifact repository.

    All methods are ``async def`` with synchronous bodies so callers can await
    them uniformly regardless of the active backend.

    Attributes
    ----------
    _artifacts : dict[str, ArtifactRecord]
        Internal storage keyed by ``artifact_id`` (insertion-ordered).
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactRecord] = {}

    async def create_snapshot(
        self,
        project_id: str,
        stage: ArtifactStage | str,
        content: dict | str,
        author_id: Optional[UUID] = None,
        author_email: Optional[str] = None,
        preview_url: Optional[str] = None,
    ) -> ArtifactRecord:
        artifact_id = f"ART-{uuid.uuid4().hex[:12].upper()}"
        record = ArtifactRecord(
            artifact_id=artifact_id,
            project_id=project_id,
            stage=_stage_value(stage),
            status="signed_off",
            content=_serialize_content(content),
            preview_url=preview_url,
            created_at=datetime.now(timezone.utc),
            author_id=author_id,
            author=author_email,
        )
        self._artifacts[artifact_id] = record
        logger.info(
            "Created artifact %s for project %s at stage %s.",
            artifact_id,
            project_id,
            record.stage,
        )
        return record

    async def list_for_project(self, project_id: str) -> list[ArtifactRecord]:
        items = [r for r in self._artifacts.values() if r.project_id == project_id]
        # stable sort preserves insertion order for equal timestamps
        return sorted(items, key=lambda r: r.created_at)

    async def get(self, artifact_id: str) -> Optional[ArtifactRecord]:
        return self._artifacts.get(artifact_id)

    def clear(self) -> None:
        """Remove all artifacts (test isolation helper)."""
        self._artifacts.clear()


# ── PostgreSQL implementation ─────────────────────────────────────────────────


class PostgresArtifactStore:
    """
    PostgreSQL-backed artifact repository using async SQLAlchemy.

    Each method opens its own session via ``get_session_maker()``, mirroring
    ``PostgresProjectStore``.
    """

    async def create_snapshot(
        self,
        project_id: str,
        stage: ArtifactStage | str,
        content: dict | str,
        author_id: Optional[UUID] = None,
        author_email: Optional[str] = None,
        preview_url: Optional[str] = None,
    ) -> ArtifactRecord:
        from db.session import get_session_maker
        from db.models.artifact import Artifact

        stage_enum = stage if isinstance(stage, ArtifactStage) else ArtifactStage(stage)

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = Artifact(
                project_id=project_id,
                stage=stage_enum,
                status="signed_off",
                content=_serialize_content(content),
                preview_url=preview_url,
                author_id=author_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return ArtifactRecord(
                artifact_id=row.artifact_id,
                project_id=row.project_id,
                stage=row.stage.value,
                status=row.status,
                content=row.content,
                preview_url=row.preview_url,
                created_at=row.created_at,
                author_id=row.author_id,
                author=author_email,
            )

    async def list_for_project(self, project_id: str) -> list[ArtifactRecord]:
        from db.session import get_session_maker
        from db.models.artifact import Artifact
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        session_maker = get_session_maker()
        async with session_maker() as session:
            stmt = (
                select(Artifact)
                .options(selectinload(Artifact.author))
                .where(Artifact.project_id == project_id)
                .order_by(Artifact.created_at)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_record(r) for r in rows]

    async def get(self, artifact_id: str) -> Optional[ArtifactRecord]:
        from db.session import get_session_maker
        from db.models.artifact import Artifact
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        session_maker = get_session_maker()
        async with session_maker() as session:
            stmt = (
                select(Artifact)
                .options(selectinload(Artifact.author))
                .where(Artifact.artifact_id == artifact_id)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return self._to_record(row)

    def _to_record(self, row: object) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row.artifact_id,  # type: ignore[attr-defined]
            project_id=row.project_id,  # type: ignore[attr-defined]
            stage=row.stage.value,  # type: ignore[attr-defined]
            status=row.status,  # type: ignore[attr-defined]
            content=row.content,  # type: ignore[attr-defined]
            preview_url=row.preview_url,  # type: ignore[attr-defined]
            created_at=row.created_at,  # type: ignore[attr-defined]
            author_id=row.author_id,  # type: ignore[attr-defined]
            author=row.author.email if row.author else None,  # type: ignore[attr-defined]
        )


def make_artifact_store() -> MemoryArtifactStore | PostgresArtifactStore:
    """Instantiate and return the configured artifact store backend."""
    from config import settings

    if settings.PROJECT_STORE_BACKEND == "postgres":
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL must be configured in your environment or .env file "
                "when PROJECT_STORE_BACKEND is set to 'postgres'."
            )
        return PostgresArtifactStore()
    return MemoryArtifactStore()


artifact_store = make_artifact_store()
