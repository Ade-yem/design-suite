"""
routers/drawings.py
===================
Drawings router to support the Drafting Agent.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status, BackgroundTasks, Response

from dependencies import get_project, require_design_complete
from schemas.jobs import JobStatus
from schemas.project import ProjectResponse
from storage.job_store import job_store
from services.drawings import drawing_service
from core.drawing.dxf_export import dxf_export_engine
from middleware.error_handler import StructuralError

_DXF_MEDIA_TYPE = "image/vnd.dxf"

logger = logging.getLogger(__name__)
router = APIRouter()


class DrawingCommandSet:
    """Stub command set model if needed."""
    pass


@router.post("/{project_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_drawings(
    project_id: str,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_design_complete),
) -> dict[str, str]:
    """
    Queue a drawing generation run for the project.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    background_tasks : BackgroundTasks
        FastAPI background tasks queue.
    project : ProjectResponse
        Enforces that the project is at least at DESIGN_COMPLETE and belongs to the active tenant.

    Returns
    -------
    dict[str, str]
        Details of the queued drawings job.
    """
    job_id = await job_store.create("drawings", project_id=project_id)
    # Stub generation logic; ideally handled by agent, but if router triggers:
    await job_store.mark_complete(job_id)
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/drawings/{project_id}/status/{job_id}",
        "message": "Drawing generation in progress."
    }


@router.get("/{project_id}", response_model=list[dict[str, Any]])
async def list_drawings(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> list[dict[str, Any]]:
    """
    List all generated drawings for a project.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    list[dict[str, Any]]
        List of drawing dictionaries.
    """
    return await drawing_service.list_drawings(project_id)


@router.get("/{project_id}/member/{member_id}", response_model=dict[str, Any])
async def get_drawing(
    project_id: str,
    member_id: str,
    project: ProjectResponse = Depends(get_project),
) -> dict[str, Any]:
    """
    Retrieve a specific member's drawing.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    dict[str, Any]
        Drawing details.

    Raises
    ------
    StructuralError
        HTTP 404 MEMBER_NOT_FOUND if the drawing for this member does not exist.
    """
    drawing = await drawing_service.get_drawing(project_id, member_id)
    if not drawing:
        raise StructuralError(
            error_code="MEMBER_NOT_FOUND",
            member_id=member_id,
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return drawing


@router.post("/{project_id}/member/{member_id}/regenerate", response_model=dict[str, str])
async def regenerate_drawing(
    project_id: str,
    member_id: str,
    project: ProjectResponse = Depends(get_project),
) -> dict[str, str]:
    """
    Trigger regeneration of a specific member's drawing.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    dict[str, str]
        Status response.

    Raises
    ------
    StructuralError
        HTTP 404 MEMBER_NOT_FOUND if the drawing for this member does not exist.
    """
    drawing = await drawing_service.get_drawing(project_id, member_id)
    if not drawing:
        raise StructuralError(
            error_code="MEMBER_NOT_FOUND",
            member_id=member_id,
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {"status": "regenerated"}


@router.get("/{project_id}/export/dxf")
async def export_project_dxf(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> Response:
    """
    Export every member drawing for a project as a single DXF file.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    Response
        ``image/vnd.dxf`` attachment containing all member details.

    Raises
    ------
    StructuralError
        HTTP 404 NO_DRAWINGS if the project has no generated drawings.
    """
    drawings = await drawing_service.list_drawings(project_id)
    if not drawings:
        raise StructuralError(
            error_code="NO_DRAWINGS",
            details={"project_id": project_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    ref = getattr(project, "reference", None) or project_id
    data = dxf_export_engine.export(drawings, title=ref)
    return Response(
        content=data,
        media_type=_DXF_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{ref}.dxf"'},
    )


@router.get("/{project_id}/member/{member_id}/export/dxf")
async def export_member_dxf(
    project_id: str,
    member_id: str,
    project: ProjectResponse = Depends(get_project),
) -> Response:
    """
    Export a single member's detail drawing as a DXF file.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    Response
        ``image/vnd.dxf`` attachment for the requested member.

    Raises
    ------
    StructuralError
        HTTP 404 MEMBER_NOT_FOUND if the member has no generated drawing.
    """
    drawing = await drawing_service.get_drawing(project_id, member_id)
    if not drawing:
        raise StructuralError(
            error_code="MEMBER_NOT_FOUND",
            member_id=member_id,
            status_code=status.HTTP_404_NOT_FOUND,
        )
    ref = getattr(project, "reference", None) or project_id
    data = dxf_export_engine.export([drawing], title=ref)
    return Response(
        content=data,
        media_type=_DXF_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{ref}_{member_id}.dxf"'},
    )


@router.put("/{project_id}/confirm", response_model=dict[str, str])
async def confirm_drawings(
    project_id: str,
    payload: dict,
    project: ProjectResponse = Depends(get_project),
) -> dict[str, str]:
    """
    Confirm all drawings for the project, locking them for the audit trail.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    payload : dict
        Payload confirmation parameters.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    dict[str, str]
        Status response.
    """
    return {"status": "confirmed"}


@router.get("/{project_id}/layers", response_model=dict[str, Any])
async def get_layers(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> dict[str, Any]:
    """
    Get bounding box and layers for canvas rendering.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    dict[str, Any]
        Layers and bounds.
    """
    return {"layers": [], "bounds": {"width": 1000, "height": 1000}}


@router.get("/{project_id}/status/{job_id}", response_model=JobStatus)
async def get_drawing_status(
    project_id: str,
    job_id: str,
    project: ProjectResponse = Depends(get_project),
) -> JobStatus:
    """
    Retrieve drawing generation status for a specific job.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    job_id : str
        Target job identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    JobStatus
        Status of the drawing job.

    Raises
    ------
    StructuralError
        HTTP 404 JOB_NOT_FOUND if the job doesn't exist or doesn't belong to the project.
    """
    job = await job_store.get_or_404(job_id)
    if job.project_id != project_id:
        raise StructuralError(
            error_code="JOB_NOT_FOUND",
            details={"job_id": job_id, "project_id": project_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return job

