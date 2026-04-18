"""
routers/files.py
================
File upload router — receives DXF / PDF files, triggers async parsing,
and manages the geometry verification gate (Safety Gate 1).

Endpoints
---------
POST   /api/v1/files/upload/{project_id}      Upload DXF or PDF file
GET    /api/v1/files/{project_id}/parsed       Get parsed structural JSON
PUT    /api/v1/files/{project_id}/verify       Human confirms parsed geometry  ← GATE
GET    /api/v1/files/{project_id}/scale        Get detected scale / units
PUT    /api/v1/files/{project_id}/scale        User confirms / corrects scale
GET    /api/v1/files/{project_id}/parse-status Poll async parsing job status

Gate enforcement
----------------
``PUT /verify`` is the mandatory human-in-the-loop gate (Safety Gate 1).
Until it returns ``{"status": "verified"}``, the loading, analysis, and design
endpoints will reject requests for this project.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, status
from pydantic import BaseModel, Field

from dependencies import get_project, require_file_uploaded
from middleware.error_handler import StructuralError
from schemas.project import ProjectResponse, ProjectStatus
from storage.file_handler import file_handler
from storage.job_store import job_store
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# In-process parsed-geometry cache  (swap with Redis / DB in production)
_parsed_store: dict[str, dict[str, Any]] = {}
_scale_store: dict[str, dict[str, Any]] = {}


# ─── Request / Response models ────────────────────────────────────────────────


class GeometryVerificationRequest(BaseModel):
    """
    Request body for PUT /api/v1/files/{project_id}/verify.

    Attributes
    ----------
    confirmed : bool
        Must be True — engineer explicitly accepts the parsed geometry.
    corrections : list[dict] | None
        Optional list of member-level corrections to apply before advancing.
    notes : str
        Free-text note logged alongside the confirmation.
    """

    confirmed: bool = Field(..., description="Must be True to pass the safety gate.")
    corrections: Optional[list[dict[str, Any]]] = Field(
        None, description="Member geometry corrections to apply."
    )
    notes: str = Field("", description="Engineer's confirmation notes.")


class ScaleCorrectionRequest(BaseModel):
    """
    Request body for PUT /api/v1/files/{project_id}/scale.

    Attributes
    ----------
    scale_factor : float
        Numeric scale factor (e.g. 0.001 to convert mm DXF units to metres).
    unit_label : str
        Human-readable unit label (e.g. ``"mm"`` or ``"m"``).
    confirmed : bool
        True when the engineer accepts the scale.
    """

    scale_factor: float = Field(..., gt=0, description="Numeric scale factor.")
    unit_label: str = Field("mm", description="Unit label (mm | m | custom).")
    confirmed: bool = Field(False, description="Acceptance flag.")


class UploadResponse(BaseModel):
    """
    Immediate response for POST /api/v1/files/upload/{project_id}.

    Attributes
    ----------
    message : str
        Status message.
    job_id : str
        Async parsing job identifier.
    status_url : str
        URL to poll for parse completion.
    """

    message: str
    job_id: str
    status_url: str


# ─── Background parse task ────────────────────────────────────────────────────


async def _parse_file_background(
    project_id: str,
    file_path: str,
    job_id: str,
) -> None:
    """
    Background task: invoke the Vision Agent parsing pipeline for a DXF/PDF file.

    Results are cached in ``_parsed_store[project_id]`` and the job status
    updated so that the frontend can display progress.

    Parameters
    ----------
    project_id : str
        Owning project.
    file_path : str
        Absolute filesystem path to the uploaded file.
    job_id : str
        Job ID corresponding to this parse operation.
    """
    job_store.mark_running(job_id, "Parsing file…")
    try:
        # ── Stub: replace with actual Vision Agent / ezdxf parsing call ────
        # from services.agents.parser import parse_dxf
        # parsed = await parse_dxf(file_path)
        parsed: dict[str, Any] = {
            "members": [],
            "scale": {"factor": 0.001, "unit": "mm", "detected": True},
            "raw_entity_count": 0,
            "parse_warnings": [],
            "file_path": file_path,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        }
        _parsed_store[project_id] = parsed
        _scale_store[project_id] = parsed["scale"]

        # Advance project status
        project_store.advance_status(project_id, ProjectStatus.FILE_UPLOADED)
        job_store.mark_complete(job_id, result_url=f"/api/v1/files/{project_id}/parsed")
        logger.info("Parsing complete for project %s.", project_id)

    except Exception as exc:
        logger.exception("Parsing failed for project %s.", project_id)
        job_store.mark_failed(job_id, errors=[str(exc)])


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/upload/{project_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_file(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project: ProjectResponse = Depends(get_project),
) -> UploadResponse:
    """
    Upload a DXF or PDF file and trigger asynchronous Vision Agent parsing.

    The endpoint returns immediately with a ``job_id``.  Poll ``status_url`` to
    track parse progress.  When parsing completes the project advances to
    ``FILE_UPLOADED`` status.

    Parameters
    ----------
    project_id : str
        Target project.
    background_tasks : BackgroundTasks
        FastAPI background task queue.
    file : UploadFile
        Uploaded file (DXF or PDF).
    project : ProjectResponse
        Gate dependency confirming the project exists.

    Returns
    -------
    UploadResponse
        ``job_id`` and ``status_url`` for polling.

    Raises
    ------
    StructuralError
        ``UNSUPPORTED_FILE`` — wrong file type.
        ``FILE_TOO_LARGE``  — exceeds 50 MB.
    """
    saved_path = await file_handler.save(project_id, file)
    job_id = job_store.create("parsing", project_id=project_id)
    background_tasks.add_task(
        _parse_file_background,
        project_id=project_id,
        file_path=str(saved_path),
        job_id=job_id,
    )
    logger.info(
        "File '%s' uploaded for project %s. Parse job: %s.",
        file.filename,
        project_id,
        job_id,
    )
    return UploadResponse(
        message="File uploaded. Parsing in progress.",
        job_id=job_id,
        status_url=f"/api/v1/files/{project_id}/parse-status/{job_id}",
    )


@router.get("/{project_id}/parse-status/{job_id}")
def get_parse_status(project_id: str, job_id: str) -> dict:
    """
    Poll the status of an async parsing job.

    Parameters
    ----------
    project_id : str
        Owning project.
    job_id : str
        Parsing job identifier.

    Returns
    -------
    dict
        JobStatus dict for the parse job.
    """
    job = job_store.get_or_404(job_id)
    return job.model_dump()


@router.get("/{project_id}/parsed")
def get_parsed_geometry(
    project_id: str,
    project: ProjectResponse = Depends(require_file_uploaded),
) -> dict:
    """
    Return the parsed structural JSON produced by the Vision Agent.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Gate dependency — requires ``FILE_UPLOADED`` status.

    Returns
    -------
    dict
        Parsed geometry including detected members, scale, and warnings.

    Raises
    ------
    StructuralError
        HTTP 404 if parsing has not completed yet.
    """
    parsed = _parsed_store.get(project_id)
    if parsed is None:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="parsing",
            details={"reason": "Parse result not available — parsing may still be in progress."},
            status_code=404,
        )
    return parsed


@router.put("/{project_id}/verify")
async def verify_geometry(
    project_id: str,
    payload: GeometryVerificationRequest,
    project: ProjectResponse = Depends(require_file_uploaded),
) -> dict:
    """
    Human-in-the-loop Safety Gate 1: engineer confirms parsed geometry.

    Until this endpoint is called with ``confirmed: true``, no loading or
    analysis endpoints will accept requests for this project.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : GeometryVerificationRequest
        Must contain ``confirmed = True``.
    project : ProjectResponse
        Gate dependency — project must have a file uploaded.

    Returns
    -------
    dict
        ``{status, member_count, verified_at}``.

    Raises
    ------
    StructuralError
        HTTP 400 if ``confirmed`` is False.
    """
    if not payload.confirmed:
        raise StructuralError(
            "GATE_NOT_PASSED",
            stage="geometry_verification",
            details={"reason": "Field 'confirmed' must be true to pass this gate."},
            status_code=400,
        )

    # Apply any corrections to the cached parsed geometry
    if payload.corrections:
        parsed = _parsed_store.get(project_id, {})
        # Merge corrections (stub — Vision Agent or service layer handles merging)
        parsed["user_corrections"] = payload.corrections
        _parsed_store[project_id] = parsed

    # Advance pipeline
    project_store.advance_status(project_id, ProjectStatus.GEOMETRY_VERIFIED)

    parsed = _parsed_store.get(project_id, {})
    member_count = len(parsed.get("members", []))

    logger.info(
        "Geometry verified for project %s. %d member(s) confirmed. Notes: %s",
        project_id,
        member_count,
        payload.notes or "(none)",
    )
    return {
        "status": "verified",
        "member_count": member_count,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{project_id}/scale")
def get_scale(
    project_id: str,
    project: ProjectResponse = Depends(require_file_uploaded),
) -> dict:
    """
    Return the scale / unit information detected during parsing.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    dict
        ``{factor, unit, detected, confirmed}``
    """
    scale = _scale_store.get(project_id)
    if scale is None:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="scale_detection",
            details={"reason": "Scale data not yet available."},
            status_code=404,
        )
    return scale


@router.put("/{project_id}/scale")
def confirm_scale(
    project_id: str,
    payload: ScaleCorrectionRequest,
    project: ProjectResponse = Depends(require_file_uploaded),
) -> dict:
    """
    User confirms or corrects the detected scale / unit factor.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : ScaleCorrectionRequest
        Scale correction details.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    dict
        Updated scale record.
    """
    _scale_store[project_id] = {
        "factor": payload.scale_factor,
        "unit": payload.unit_label,
        "detected": False,
        "confirmed": payload.confirmed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "Scale updated for project %s: factor=%s unit=%s.",
        project_id,
        payload.scale_factor,
        payload.unit_label,
    )
    return _scale_store[project_id]
