"""
routers/projects.py
===================
Project CRUD router — the top-level entity that all other resources belong to.

Endpoints
---------
POST   /api/v1/projects/                    Create new project
GET    /api/v1/projects/                    List all projects
GET    /api/v1/projects/{project_id}        Get project details
PUT    /api/v1/projects/{project_id}        Update project metadata
DELETE /api/v1/projects/{project_id}        Delete project
GET    /api/v1/projects/{project_id}/status Get pipeline stage status

Gate enforcement
----------------
No gate enforcement on these endpoints — they manage the project entity itself.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from dependencies import get_project
from schemas.project import (
    BaseResponse,
    PipelineStatusResponse,
    ProjectCreate,
    ProjectListItem,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
)
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NEXT_ACTION_MAP: dict[ProjectStatus, str] = {
    ProjectStatus.CREATED:           "upload_file",
    ProjectStatus.FILE_UPLOADED:     "verify_geometry",
    ProjectStatus.GEOMETRY_VERIFIED: "define_loading",
    ProjectStatus.LOADING_DEFINED:   "run_analysis",
    ProjectStatus.ANALYSIS_COMPLETE: "run_design",
    ProjectStatus.DESIGN_COMPLETE:   "generate_report",
    ProjectStatus.REPORT_GENERATED:  "complete",
}

_GATE_LABELS: tuple[str, ...] = (
    "geometry_verified",
    "loading_confirmed",
    "analysis_complete",
    "design_complete",
    "report_approved",
)


def _build_gates(status_ordinal: int) -> dict[str, bool]:
    """Build a gate bool map from the numeric pipeline status ordinal."""
    thresholds = (
        ProjectStatus.GEOMETRY_VERIFIED,
        ProjectStatus.LOADING_DEFINED,
        ProjectStatus.ANALYSIS_COMPLETE,
        ProjectStatus.DESIGN_COMPLETE,
        ProjectStatus.REPORT_GENERATED,
    )
    return {label: status_ordinal >= thresh for label, thresh in zip(_GATE_LABELS, thresholds)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate) -> ProjectResponse:
    """
    Create a new project entry and initialize the pipeline state machine.

    Parameters
    ----------
    payload : ProjectCreate
        Project metadata including name, reference, client, and design code.

    Returns
    -------
    ProjectResponse
        Newly created project with ``pipeline_status = "created"``.
    """
    project = project_store.create(payload)
    logger.info("Project created: %s (%s)", project.project_id, project.name)
    return project


@router.get("/", response_model=list[ProjectListItem])
def list_projects() -> list[ProjectListItem]:
    """
    Return lightweight summaries of all projects, most recently updated first.

    Returns
    -------
    list[ProjectListItem]
        Summary list of all registered projects.
    """
    return project_store.list_all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project_detail(project: ProjectResponse = Depends(get_project)) -> ProjectResponse:
    """
    Return full project details including current pipeline status.

    Parameters
    ----------
    project : ProjectResponse
        Resolved via ``get_project`` dependency (404 if not found).

    Returns
    -------
    ProjectResponse
    """
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    project: ProjectResponse = Depends(get_project),
) -> ProjectResponse:
    """
    Apply a partial update to project metadata.

    Only fields supplied in the request body are modified.

    Parameters
    ----------
    project_id : str
        Path parameter — project to update.
    payload : ProjectUpdate
        Fields to change.
    project : ProjectResponse
        Gate dependency — confirms the project exists.

    Returns
    -------
    ProjectResponse
        Updated project.
    """
    updated = project_store.update(project_id, payload)
    logger.info("Project updated: %s", project_id)
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> None:
    """
    Delete a project and all associated data (members, files, jobs).

    Parameters
    ----------
    project_id : str
        Project to delete.
    project : ProjectResponse
        Gate dependency.
    """
    from storage.file_handler import file_handler

    project_store.delete(project_id)
    file_handler.delete(project_id)
    logger.info("Project deleted: %s", project_id)


@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
def get_pipeline_status(project: ProjectResponse = Depends(get_project)) -> PipelineStatusResponse:
    """
    Return the pipeline stage completion status for the project.

    Parameters
    ----------
    project : ProjectResponse
        Resolved project entity.

    Returns
    -------
    PipelineStatusResponse
        Gates dict, next action, and blocking issues.
    """
    current_status = ProjectStatus(project.pipeline_status_ordinal)
    gates = _build_gates(project.pipeline_status_ordinal)

    return PipelineStatusResponse(
        project_id=project.project_id,
        current_stage=project.pipeline_status,
        next_action=_NEXT_ACTION_MAP.get(current_status, "complete"),
        gates=gates,
        blocking_issues=[],
        completed_members=project.member_count,
        failed_members=0,
        last_updated=project.updated_at,
    )
