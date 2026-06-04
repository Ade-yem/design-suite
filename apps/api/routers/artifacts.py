"""
routers/artifacts.py
====================
Artifact snapshot retrieval and inspection.

Endpoints
---------
GET    /api/v1/artifacts/{project_id}     List all artifacts for a project
GET    /api/v1/artifacts/detail/{artifact_id}    Retrieve a single artifact
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_session
from middleware.error_handler import StructuralError
from services.artifacts import artifact_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ArtifactResponse(BaseModel):
    """
    API response for a single artifact snapshot.

    Attributes
    ----------
    artifact_id : str
        Unique snapshot identifier.
    project_id : str
        Owning project.
    stage : str
        Pipeline stage (parsing, verification, loading, analysis, design, drawing).
    status : str
        Status badge (signed_off, in_review, pending).
    created_at : str
        ISO 8601 timestamp.
    author : str | None
        Email of the engineer who approved the gate.
    content : dict | None
        The snapshot content (parsed geometry JSON, etc.).
        Large artifacts can omit this in list responses.
    preview_url : str | None
        Optional URL to a rendered preview.
    download_url : str | None
        URL to download the artifact (e.g., as JSON or PDF).
    """

    artifact_id: str
    project_id: str
    stage: str
    status: str
    created_at: str
    author: Optional[str] = None
    content: Optional[dict] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None


@router.get("/{project_id}")
async def list_artifacts(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[ArtifactResponse]:
    """
    List all artifacts (snapshots) for a project.

    Parameters
    ----------
    project_id : str
        Target project.

    Returns
    -------
    list[ArtifactResponse]
        All snapshots, ordered by creation date. Content is omitted from list responses.
    """
    artifacts = await artifact_service.get_artifacts_for_project(session, project_id)

    return [
        ArtifactResponse(
            artifact_id=a.artifact_id,
            project_id=a.project_id,
            stage=a.stage.value,
            status=a.status,
            created_at=a.created_at.isoformat(),
            author=a.author.email if a.author else None,
            content=None,  # Omit from list responses
            preview_url=a.preview_url,
            download_url=f"/api/v1/artifacts/download/{a.artifact_id}",
        )
        for a in artifacts
    ]


@router.get("/detail/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
) -> ArtifactResponse:
    """
    Retrieve a single artifact with full content.

    Parameters
    ----------
    artifact_id : str
        Target artifact.

    Returns
    -------
    ArtifactResponse
        Complete snapshot including content.

    Raises
    ------
    StructuralError
        If the artifact is not found (404).
    """
    artifact = await artifact_service.get_artifact_by_id(session, artifact_id)

    if not artifact:
        raise StructuralError("NOT_FOUND", stage="artifacts", status_code=404)

    # Parse content JSON
    content = None
    if artifact.content:
        try:
            content = json.loads(artifact.content)
        except json.JSONDecodeError:
            pass

    return ArtifactResponse(
        artifact_id=artifact.artifact_id,
        project_id=artifact.project_id,
        stage=artifact.stage.value,
        status=artifact.status,
        created_at=artifact.created_at.isoformat(),
        author=artifact.author.email if artifact.author else None,
        content=content,
        preview_url=artifact.preview_url,
        download_url=f"/api/v1/artifacts/download/{artifact.artifact_id}",
    )
