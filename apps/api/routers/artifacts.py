"""
routers/artifacts.py
====================
Artifact snapshot retrieval and inspection.

Endpoints
---------
GET    /api/v1/artifacts/{project_id}        List all artifacts for a project
GET    /api/v1/artifacts/detail/{artifact_id} Retrieve a single artifact

Persistence is delegated entirely to ``storage.artifact_store`` (memory or
postgres backend) — this router only handles HTTP concerns.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import current_active_user
from db.models.user import User
from dependencies import get_project
from middleware.error_handler import StructuralError
from schemas.artifact import ArtifactRecord
from schemas.project import ProjectResponse
from storage.artifact_store import artifact_store
from storage.project_store import project_store

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
        Omitted from list responses; populated by the detail endpoint.
    preview_url : str | None
        Optional URL to a rendered preview.
    download_url : str | None
        URL to download the artifact.
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


def _to_response(record: ArtifactRecord, *, include_content: bool) -> ArtifactResponse:
    """Map an ArtifactRecord onto the public ArtifactResponse envelope."""
    content: Optional[dict] = None
    if include_content and record.content:
        try:
            content = json.loads(record.content)
        except json.JSONDecodeError:
            content = None

    return ArtifactResponse(
        artifact_id=record.artifact_id,
        project_id=record.project_id,
        stage=record.stage,
        status=record.status,
        created_at=record.created_at.isoformat(),
        author=record.author,
        content=content,
        preview_url=record.preview_url,
        download_url=f"/api/v1/artifacts/download/{record.artifact_id}",
    )


@router.get("/{project_id}")
async def list_artifacts(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> list[ArtifactResponse]:
    """
    List all artifacts (snapshots) for a project.

    Content is omitted from list responses; fetch the detail endpoint for the
    full payload.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Resolved + org-scoped project (raises 404 if not accessible).

    Returns
    -------
    list[ArtifactResponse]
        All snapshots, ordered by creation date.
    """
    records = await artifact_store.list_for_project(project_id)
    return [_to_response(r, include_content=False) for r in records]


@router.get("/detail/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    user: User = Depends(current_active_user),
) -> ArtifactResponse:
    """
    Retrieve a single artifact with full content.

    Parameters
    ----------
    artifact_id : str
        Target artifact.
    user : User
        Authenticated user (auth required).

    Returns
    -------
    ArtifactResponse
        Complete snapshot including content.

    Raises
    ------
    StructuralError
        HTTP 404 if the artifact is not found.
    """
    record = await artifact_store.get(artifact_id)
    if record is None:
        raise StructuralError(
            "ARTIFACT_NOT_FOUND",
            stage="artifacts",
            details={"artifact_id": artifact_id},
            status_code=404,
        )
    # Enforce tenant check
    await project_store.get_or_404(record.project_id, organisation_id=user.organisation_id)
    return _to_response(record, include_content=True)
