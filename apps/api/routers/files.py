"""
routers/files.py
================
File upload router — receives DXF / PDF files, delegates all parsing and
geometry management to ``services.files``, and enforces Safety Gate 1.

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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from auth.dependencies import current_active_user
from db.models.user import User
from dependencies import get_project, require_file_uploaded
from middleware.error_handler import StructuralError
from schemas.project import ProjectResponse, ProjectStatus
from services.files import file_service
from storage.artifact_store import artifact_store
from storage.file_handler import file_handler
from storage.job_store import job_store

logger = logging.getLogger(__name__)
router = APIRouter()


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
    last_updated_at : str | None
        The ISO timestamp of the last known update for concurrency checks.
    """

    confirmed: bool = Field(..., description="Must be True to pass the safety gate.")
    corrections: Optional[list[dict[str, Any]]] = Field(
        None, description="Member geometry corrections to apply."
    )
    notes: str = Field("", description="Engineer's confirmation notes.")
    last_updated_at: Optional[str] = Field(
        None, description="The ISO timestamp of the last known update for concurrency checks."
    )


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


class ProjectFileMetadata(BaseModel):
    """
    Metadata for an uploaded project reference drawing file.

    Attributes
    ----------
    filename : str
        Sanitized safe stored filename (with timestamp prefix).
    original_name : str
        User-friendly original filename without timestamp prefix.
    size_bytes : int
        File size in bytes.
    file_type : str
        Drawing type ('dxf' | 'pdf' | 'unknown').
    download_url : str
        Relative endpoint path to stream the file.
    """

    filename: str = Field(..., description="Unique safe stored filename.")
    original_name: str = Field(..., description="User-friendly original filename.")
    size_bytes: int = Field(..., description="File size in bytes.")
    file_type: str = Field(..., description="Drawing type (dxf | pdf | unknown).")
    download_url: str = Field(..., description="Download API path.")


# ─── Background parse task ────────────────────────────────────────────────────


async def _parse_file_background(
    project_id: str,
    file_path: str,
    job_id: str,
    pdf_path: Optional[str] = None,
) -> None:
    """
    Background task: invoke ``file_service.parse()`` then run LLM member
    extraction if the low-level parser found no classified members.

    Parameters
    ----------
    project_id : str
        Owning project.
    file_path : str
        Absolute filesystem path to the uploaded file.
    job_id : str
        Job ID corresponding to this parse operation.
    pdf_path : str | None
        Optional absolute filesystem path to the uploaded reference PDF.
    """
    await job_store.mark_running(job_id, "Parsing file…")
    try:
        parsed = await file_service.parse(project_id, file_path)

        # Cache reference paths in geometry dictionary for visual grounding
        if pdf_path:
            parsed["uploaded_pdf_path"] = pdf_path

        # ezdxf extracts raw geometry only;
        if not parsed.get("members"):
            await job_store.update_progress(job_id, 60.0, "Classifying structural members…")
            from agents.parser import cross_reference_void_markers, _filter_stub_beams, _deduplicate_beams, _run_member_extraction
            from storage.project_store import project_store as _pstore

            members = await _run_member_extraction(project_id, parsed)
            members = _deduplicate_beams(members)
            members = _filter_stub_beams(members)
            members = cross_reference_void_markers(parsed["entities"], members)
            parsed["members"] = members

            await file_service.register_geometry(project_id, parsed)
            mids = [member.get("member_id") for member in members if member.get("member_id")]
            await _pstore.register_members_batch(project_id, mids)

        await job_store.mark_complete(job_id, result_url=f"/api/v1/files/{project_id}/parsed")
        logger.info("Parsing complete for project %s.", project_id)
    except Exception as exc:
        logger.exception("Parsing failed for project %s.", project_id)
        await job_store.mark_failed(job_id, errors=[str(exc)])


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
    pdf_file: Optional[UploadFile] = File(None),
    project: ProjectResponse = Depends(get_project),
) -> UploadResponse:
    """
    Upload a DXF drawing and an optional reference PDF file, triggering Vision Agent parsing.

    The endpoint returns immediately with a ``job_id``. Poll ``status_url`` to
    track parse progress. When parsing completes the project advances to
    ``FILE_UPLOADED`` status.

    Parameters
    ----------
    project_id : str
        Target project.
    background_tasks : BackgroundTasks
        FastAPI background task queue.
    file : UploadFile
        Uploaded primary drawing file (DXF).
    pdf_file : UploadFile | None
        Optional uploaded reference PDF file for layout and visual grounding.
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
    if project.pipeline_status_ordinal >= ProjectStatus.GEOMETRY_VERIFIED:
        raise StructuralError(
            "PIPELINE_ERROR",
            stage="file_upload",
            details={"reason": "Cannot upload drawing. Geometry has already been verified for this project."},
            status_code=400,
        )

    # Check if there is another parsing job active
    jobs = await job_store.list_for_project(project_id)
    if any(j.job_type == "parsing" and j.status in ("queued", "running") for j in jobs):
        raise StructuralError(
            "PIPELINE_ERROR",
            stage="file_upload",
            details={"reason": "A parsing job is already in progress for this project."},
            status_code=400,
        )

    saved_path = await file_handler.save(project_id, file)

    saved_pdf_path: Optional[str] = None
    if pdf_file:
        saved_pdf_path = await file_handler.save(project_id, pdf_file)

    job_id = await job_store.create("parsing", project_id=project_id)
    background_tasks.add_task(
        _parse_file_background,
        project_id=project_id,
        file_path=saved_path,
        job_id=job_id,
        pdf_path=saved_pdf_path,
    )
    logger.info(
        "File '%s' (PDF ref: '%s') uploaded for project %s. Parse job: %s.",
        file.filename,
        pdf_file.filename if pdf_file else "none",
        project_id,
        job_id,
    )
    return UploadResponse(
        message="File uploaded. Parsing in progress.",
        job_id=job_id,
        status_url=f"/api/v1/files/{project_id}/parse-status/{job_id}",
    )


@router.post(
    "/{project_id}/reparse",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reparse_project_files(
    project_id: str,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_file_uploaded),
) -> UploadResponse:
    """
    Re-run the Vision & Parsing Agent on already uploaded project drawing files.

    Resets the verified status and local layout changes, starting the geometry
    classification from scratch.

    Parameters
    ----------
    project_id : str
        Target project.
    background_tasks : BackgroundTasks
        FastAPI background task queue.
    project : ProjectResponse
        Gate dependency confirming a file has already been uploaded.

    Returns
    -------
    UploadResponse
        ``job_id`` and ``status_url`` for polling the background parse job.
    """
    if project.pipeline_status_ordinal >= ProjectStatus.GEOMETRY_VERIFIED:
        raise StructuralError(
            "PIPELINE_ERROR",
            stage="reparse",
            details={"reason": "Cannot reparse drawing. Geometry has already been verified for this project."},
            status_code=400,
        )

    # Check if there is another parsing job active
    jobs = await job_store.list_for_project(project_id)
    if any(j.job_type == "parsing" and j.status in ("queued", "running") for j in jobs):
        raise StructuralError(
            "PIPELINE_ERROR",
            stage="reparse",
            details={"reason": "A parsing job is already in progress for this project."},
            status_code=400,
        )

    # Retrieve already uploaded files
    filenames = file_handler.list_files(project_id)
    dxf_file = next((f for f in filenames if f.lower().endswith(".dxf")), None)
    pdf_file = next((f for f in filenames if f.lower().endswith(".pdf")), None)

    if not dxf_file:
        raise StructuralError(
            "FILE_NOT_FOUND",
            stage="reparse",
            details={"reason": "No primary DXF drawing file found for this project. Please upload one first."},
            status_code=404,
        )

    saved_path = await file_handler.get_url(project_id, dxf_file)
    if not saved_path:
        raise StructuralError(
            "FILE_NOT_FOUND",
            stage="reparse",
            details={"reason": "Could not retrieve the DXF drawing file for this project. Please try uploading it again."},
            status_code=404,
        )
    saved_pdf_path = await file_handler.get_url(project_id, pdf_file) if pdf_file else None
    # Clear cached geometry in service
    await file_service.clear(project_id)

    job_id = await job_store.create("parsing", project_id=project_id)
    background_tasks.add_task(
        _parse_file_background,
        project_id=project_id,
        file_path=saved_path,
        job_id=job_id,
        pdf_path=saved_pdf_path,
    )
    logger.info(
        "Reparse triggered for project %s (DXF: '%s', PDF ref: '%s'). Parse job: %s.",
        project_id,
        dxf_file,
        pdf_file if pdf_file else "none",
        job_id,
    )
    return UploadResponse(
        message="Reparsing project drawing initiated. Parsing in progress.",
        job_id=job_id,
        status_url=f"/api/v1/files/{project_id}/parse-status/{job_id}",
    )


@router.get("/{project_id}/parse-status/{job_id}")
async def get_parse_status(
    project_id: str,
    job_id: str,
    project: ProjectResponse = Depends(get_project),
) -> dict:
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
    job = await job_store.get_or_404(job_id)
    return job.model_dump()


@router.get("/{project_id}/parsed")
async def get_parsed_geometry(
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
    await file_service.ensure_cached(project_id)
    try:
        return await file_service.get_parsed(project_id)
    except KeyError as exc:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="parsing",
            details={"reason": str(exc)},
            status_code=404,
        ) from exc


@router.put("/{project_id}/verify")
async def verify_geometry(
    project_id: str,
    payload: GeometryVerificationRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_file_uploaded),
    user: User = Depends(current_active_user),
) -> dict:
    """
    Human-in-the-loop Safety Gate 1: engineer confirms parsed geometry.

    Until this endpoint is called with ``confirmed: true``, no loading or
    analysis endpoints will accept requests for this project.

    On confirmation, freezes an immutable snapshot (artifact) of the verified
    geometry for the audit trail.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : GeometryVerificationRequest
        Must contain ``confirmed = True``.
    background_tasks : BackgroundTasks
        FastAPI background task manager.
    project : ProjectResponse
        Gate dependency — project must have a file uploaded.
    user : User
        Authenticated user — recorded as the snapshot author.

    Returns
    -------
    dict
        ``{status, member_count, verified_at, artifact_id}``.

    Raises
    ------
    StructuralError
        HTTP 400 if ``confirmed`` is False or parsing is active.
    """
    if not payload.confirmed:
        raise StructuralError(
            "GATE_NOT_PASSED",
            stage="geometry_verification",
            details={"reason": "Field 'confirmed' must be true to pass this gate."},
            status_code=400,
        )

    # Concurrency check: Reject if parsing job is active
    jobs = await job_store.list_for_project(project_id)
    if any(j.job_type == "parsing" and j.status in ("queued", "running") for j in jobs):
        raise StructuralError(
            "PIPELINE_ERROR",
            stage="geometry_verification",
            details={"reason": "Cannot verify geometry while a parsing job is currently active."},
            status_code=400,
        )

    try:
        result = await file_service.verify_geometry(
            project_id,
            corrections=payload.corrections,
            notes=payload.notes,
            last_updated_at=payload.last_updated_at,
        )

        # Freeze an immutable snapshot of the verified geometry (audit trail).
        from db.models.artifact import ArtifactStage

        # Clean up any existing verification snapshots for this project first
        # to prevent duplicate/stale artifacts from retry attempts.
        if hasattr(artifact_store, "_artifacts"):
            # MemoryArtifactStore
            for k in list(artifact_store._artifacts.keys()):
                art = artifact_store._artifacts[k]
                if art.project_id == project_id and art.stage == ArtifactStage.VERIFICATION.value:
                    del artifact_store._artifacts[k]
        else:
            # PostgresArtifactStore
            from db.session import get_session_maker
            from db.models.artifact import Artifact
            from sqlalchemy import delete
            
            session_maker = get_session_maker()
            async with session_maker() as session:
                stmt = delete(Artifact).where(
                    Artifact.project_id == project_id,
                    Artifact.stage == ArtifactStage.VERIFICATION
                )
                await session.execute(stmt)
                await session.commit()

        parsed_geometry = await file_service.get_parsed(project_id)
        if parsed_geometry:
            snapshot = await artifact_store.create_snapshot(
                project_id,
                ArtifactStage.VERIFICATION,
                content=parsed_geometry,
                author_id=user.id,
                author_email=user.email,
                preview_url=None,  # TODO: generate geometry diagram on approval
            )
            result["artifact_id"] = snapshot.artifact_id

    except ValueError as exc:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="geometry_verification",
            details={"reason": str(exc)},
            status_code=400,
        ) from exc

    # Write confirmation to LangGraph checkpointer state
    import agents.graph as _agent_graph
    config = {"configurable": {"thread_id": project_id}}
    await _agent_graph.app.aupdate_state(config, {"geometry_verified": True})

    # Trigger resume in the background
    from websocket import run_or_resume_graph
    background_tasks.add_task(run_or_resume_graph, project_id, None)

    return result


@router.get("/{project_id}/scale")
async def get_scale(
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
    await file_service.ensure_cached(project_id)
    try:
        return await file_service.get_scale(project_id)
    except KeyError as exc:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="scale_detection",
            details={"reason": str(exc)},
            status_code=404,
        ) from exc


@router.put("/{project_id}/scale")
async def confirm_scale(
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
    return await file_service.confirm_scale(
        project_id,
        scale_factor=payload.scale_factor,
        unit_label=payload.unit_label,
    )


# ─── File Listing & Downloading Endpoints ─────────────────────────────────────

@router.get("/{project_id}/files", response_model=list[ProjectFileMetadata])
async def list_project_files(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> list[ProjectFileMetadata]:
    """
    List all uploaded DXF and PDF drawings associated with a project.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    project : ProjectResponse
        Project validation dependency.

    Returns
    -------
    list[ProjectFileMetadata]
        List of reference drawing file records.
    """
    filenames = file_handler.list_files(project_id)
    files = []
    for fname in filenames:
        url = await file_handler.get_url(project_id, fname)
        if not url:
            continue

        original_name = fname
        parts = fname.split("_", 1)
        if len(parts) > 1 and parts[0].isdigit():
            original_name = parts[1]

        suffix = Path(fname).suffix.lower()
        file_type = "dxf" if suffix == ".dxf" else "pdf" if suffix == ".pdf" else "unknown"

        size_bytes = 0
        if os.path.exists(url):
            size_bytes = os.path.getsize(url)

        files.append(
            ProjectFileMetadata(
                filename=fname,
                original_name=original_name,
                size_bytes=size_bytes,
                file_type=file_type,
                download_url=f"/api/v1/files/{project_id}/download/{fname}",
            )
        )
    return files


@router.get("/{project_id}/download/{filename}")
async def download_project_file(
    project_id: str,
    filename: str,
    project: ProjectResponse = Depends(get_project),
):
    """
    Stream or redirect to an uploaded project reference drawing file.

    Parameters
    ----------
    project_id : str
        Owning project.
    filename : str
        Unique stored name of the file to retrieve.

    Returns
    -------
    FileResponse or RedirectResponse
        File stream response for local storage, or redirect for remote storage.
    """
    url = await file_handler.get_url(project_id, filename)
    if not url:
        raise StructuralError(
            "FILE_PARSE_ERROR",
            stage="download",
            details={"reason": f"File '{filename}' does not exist."},
            status_code=404,
        )

    if os.path.exists(url):
        original_name = filename
        parts = filename.split("_", 1)
        if len(parts) > 1 and parts[0].isdigit():
            original_name = parts[1]
        return FileResponse(
            path=url,
            filename=original_name,
            media_type="application/octet-stream",
        )

    return RedirectResponse(url=url)
