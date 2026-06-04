"""
services/artifacts.py
====================
Artifact snapshot creation and retrieval.

Handles creating immutable snapshots of stage outputs (parsed geometry, etc.)
when gates are approved. Snapshots are frozen in time with author + timestamp
for audit trail and versioning.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models.artifact import Artifact, ArtifactStage

logger = logging.getLogger(__name__)


class ArtifactService:
    """Manage artifact snapshots across the pipeline."""

    async def create_snapshot(
        self,
        session: AsyncSession,
        project_id: str,
        stage: ArtifactStage,
        content: dict | str,
        author_id: Optional[UUID] = None,
        preview_url: Optional[str] = None,
    ) -> Artifact:
        """
        Create an immutable snapshot at gate approval.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        project_id : str
            Owning project.
        stage : ArtifactStage
            Pipeline stage (e.g., ArtifactStage.VERIFICATION).
        content : dict | str
            The snapshot content (geometry JSON, etc.).
            If dict, will be serialized to JSON.
        author_id : UUID | None
            User who approved the gate.
        preview_url : str | None
            Optional URL to a rendered preview.

        Returns
        -------
        Artifact
            The created snapshot record.
        """
        # Serialize content if dict
        if isinstance(content, dict):
            content_str = json.dumps(content)
        else:
            content_str = content

        artifact = Artifact(
            project_id=project_id,
            stage=stage,
            status="signed_off",
            content=content_str,
            author_id=author_id,
            preview_url=preview_url,
        )
        session.add(artifact)
        await session.flush()  # Insert but don't commit yet
        logger.info(
            "Created artifact %s for project %s at stage %s.",
            artifact.artifact_id,
            project_id,
            stage.value,
        )
        return artifact

    async def get_artifacts_for_project(
        self, session: AsyncSession, project_id: str
    ) -> list[Artifact]:
        """
        Retrieve all artifacts for a project.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        project_id : str
            Owning project.

        Returns
        -------
        list[Artifact]
            All snapshots for this project, ordered by creation date.
        """
        stmt = (
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_artifact_by_id(
        self, session: AsyncSession, artifact_id: str
    ) -> Optional[Artifact]:
        """
        Retrieve a single artifact by ID.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        artifact_id : str
            Target artifact.

        Returns
        -------
        Artifact | None
            The artifact, or None if not found.
        """
        stmt = select(Artifact).where(Artifact.artifact_id == artifact_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


artifact_service = ArtifactService()
