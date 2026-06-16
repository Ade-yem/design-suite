"""
Reports API Router
==================
FastAPI router exposing the Output & Reporting Layer endpoints.

Endpoints
---------
POST /reports/generate
    Generate HTML preview and/or PDF download for a project report.
    Accepts project metadata, member design data, and target report types.

GET /reports/{report_id}/preview
    Returns the rendered HTML for the right-panel IDE preview.

GET /reports/{report_id}/download
    Triggers WeasyPrint conversion and returns the PDF binary.

GET /reports/{report_id}/status
    Returns the generation status for async jobs.

Report Types
------------
* ``calculation_sheets`` — One calc sheet per member
* ``schedule``           — BS 8666:2020 reinforcement bar schedule
* ``quantities``         — Material take-off
* ``compliance``         — Compliance / check register
* ``summary``            — One-page project executive summary
* ``full``               — All of the above combined

Notes
-----
* Report HTML is cached in-process (``_report_store``) by ``report_id``.
* For production, replace the in-process store with Redis or filesystem storage.
* PDF conversion is done synchronously — for large reports, offload to a
  background task (FastAPI ``BackgroundTasks`` or Celery).
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from auth.dependencies import current_active_user
from db.models.user import User
from storage.project_store import project_store
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from core.reporting.normalizer import InputNormalizer, ValidationError
from core.reporting.calc_sheet import CalcSheetEngine
from core.reporting.rebar_schedule import RebarScheduleEngine
from core.reporting.quantities import MaterialQuantityEngine
from core.reporting.compliance import ComplianceReportEngine
from core.reporting.summary import ProjectSummaryEngine
from core.reporting.renderer import TemplateRenderer
from core.reporting.pdf_export import PDFExportEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

# ---------------------------------------------------------------------------
# In-process report store  (replace with persistent store in production)
# ---------------------------------------------------------------------------
_report_store: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ProjectMeta(BaseModel):
    """Project-level metadata for the report request."""

    name: str = Field(..., description="Full project title.")
    reference: str = Field(..., description="Project / job reference number.")
    client: str = Field("", description="Client / employer name.")
    engineer: str = Field("", description="Lead structural engineer name.")
    checker: str = Field("", description="Checking engineer name.")
    date: Optional[str] = Field(None, description="Issue date (ISO 8601). Defaults to today.")
    revision: str = Field("P01", description="Document revision code.")
    design_code: str = Field("BS8110", description="Primary design code (BS8110 or EC2).")
    design_code_edition: str = Field(
        "BS 8110-1:1997", description="Full edition string of the design code."
    )


class GenerateReportRequest(BaseModel):
    """
    Request body for POST /reports/generate.

    Attributes
    ----------
    project_id : str
        Caller-assigned project identifier (used for logging / cross-reference).
    project : ProjectMeta
        Project-level metadata.
    members : list[dict]
        List of designed member dicts. Each must contain:
        member_id, member_type, floor_level, design_code,
        loading_output, analysis_output, design_output.
    report_type : str
        One of: calculation_sheets | schedule | quantities | compliance | full.
    member_ids : list[str] | Literal["all"]
        Which members to include. Use "all" for all members.
    format : str
        "html" for preview only, "pdf" to also generate PDF.
    """

    project_id: str = Field(..., description="Caller project identifier.")
    project: ProjectMeta
    members: list[dict[str, Any]] = Field(
        ..., description="List of designed member data dicts."
    )
    report_type: Literal[
        "calculation_sheets", "schedule", "quantities", "compliance", "summary", "full"
    ] = Field("full", description="Which report type(s) to generate.")
    member_ids: Any = Field(
        "all",
        description='List of member IDs to include, or the string "all".',
    )
    format: Literal["html", "pdf"] = Field(
        "html", description='"html" for preview, "pdf" to also export PDF.'
    )


class GenerateReportResponse(BaseModel):
    """Response body for POST /reports/generate."""

    report_id: str
    preview_url: str
    download_url: str
    status: str
    generated_at: str
    member_count: int


# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------
_normalizer = InputNormalizer()
_calc_engine = CalcSheetEngine()
_rebar_engine = RebarScheduleEngine()
_qty_engine = MaterialQuantityEngine()
_compliance_engine = ComplianceReportEngine()
_summary_engine = ProjectSummaryEngine()
_renderer = TemplateRenderer()
_pdf_engine = PDFExportEngine()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=GenerateReportResponse, status_code=201)
async def generate_report(
    request: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_active_user),
) -> GenerateReportResponse:
    """
    Generate a structured engineering report from Design Suite JSON outputs.

    Validates and normalises member data, runs all five reporting modules,
    renders HTML templates, and (optionally) converts to PDF.

    Parameters
    ----------
    request : GenerateReportRequest
        Full report generation request including project metadata and member data.
    background_tasks : BackgroundTasks
        FastAPI background tasks queue.
    user : User
        The authenticated current user.

    Returns
    -------
    GenerateReportResponse
        ``report_id``, ``preview_url``, ``download_url``, and status.

    Raises
    ------
    400 Bad Request
        If input validation fails (missing required member fields, mixed codes).
    404 Not Found
        If the project does not exist or does not belong to the user's organisation.
    500 Internal Server Error
        If template rendering fails.
    """
    # Enforce tenant check first
    await project_store.get_or_404(request.project_id, organisation_id=user.organisation_id)

    return _build_and_store_report(
        project_id=request.project_id,
        project_meta=request.project,
        members=request.members,
        report_type=request.report_type,
        member_ids=request.member_ids,
        fmt=request.format,
        background_tasks=background_tasks,
    )


@router.post("/{project_id}/from-project", response_model=GenerateReportResponse, status_code=201)
async def generate_project_report(
    project_id: str,
    background_tasks: BackgroundTasks,
    report_type: Literal[
        "calculation_sheets", "schedule", "quantities", "compliance", "summary", "full"
    ] = "calculation_sheets",
    fmt: Literal["html", "pdf"] = "pdf",
    user: User = Depends(current_active_user),
) -> GenerateReportResponse:
    """
    Generate a report directly from a project's stored stage results.

    Unlike ``POST /reports/generate`` (which expects the caller to assemble the
    full member payload), this endpoint reads the loading, analysis and design
    outputs already stored for the project and assembles the report server-side.
    The frontend can therefore request a PDF with only the project id.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    background_tasks : BackgroundTasks
        FastAPI background tasks queue.
    report_type : str
        Which report type to generate. Defaults to ``calculation_sheets``.
    fmt : str
        ``"pdf"`` to pre-generate a PDF, ``"html"`` for preview only.
    user : User
        The authenticated current user.

    Returns
    -------
    GenerateReportResponse
        ``report_id`` plus preview/download URLs.

    Raises
    ------
    404 Not Found
        If the project does not exist / belong to the org, or has no design
        results to report on.
    400 Bad Request
        If the assembled member data fails validation.
    """
    project = await project_store.get_or_404(project_id, organisation_id=user.organisation_id)

    members = _assemble_members_from_stores(project_id, getattr(project, "design_code", "BS8110"))
    if not members:
        raise HTTPException(
            status_code=404,
            detail=f"No design results to report for project '{project_id}'. Run design first.",
        )

    project_meta = ProjectMeta(
        name=getattr(project, "name", project_id),
        reference=getattr(project, "reference", project_id) or project_id,
        client=getattr(project, "client", "") or "",
        design_code=getattr(project, "design_code", "BS8110") or "BS8110",
    )

    return _build_and_store_report(
        project_id=project_id,
        project_meta=project_meta,
        members=members,
        report_type=report_type,
        member_ids="all",
        fmt=fmt,
        background_tasks=background_tasks,
    )


@router.get("/{report_id}/preview", response_class=HTMLResponse)
async def preview_report(
    report_id: str,
    user: User = Depends(current_active_user),
) -> HTMLResponse:
    """
    Return the rendered HTML for the frontend IDE right panel.

    Parameters
    ----------
    report_id : str
        The report ID returned by ``/reports/generate``.
    user : User
        The authenticated current user.

    Returns
    -------
    HTMLResponse
        The rendered HTML document.

    Raises
    ------
    404 Not Found
        If no report with this ID exists, or if the associated project
        does not belong to the user's organisation.
    """
    store = _get_report_or_404(report_id)
    # Enforce tenant check
    await project_store.get_or_404(store["project_id"], organisation_id=user.organisation_id)
    return HTMLResponse(content=store["html"], status_code=200)


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    user: User = Depends(current_active_user),
) -> Response:
    """
    Convert the report HTML to PDF via WeasyPrint and return the binary.

    The PDF is cached on the ``_report_store`` entry after first generation.

    Parameters
    ----------
    report_id : str
        The report ID returned by ``/reports/generate``.
    user : User
        The authenticated current user.

    Returns
    -------
    Response
        PDF binary with ``application/pdf`` content type.

    Raises
    ------
    404 Not Found
        If the report ID does not exist, or if the associated project
        does not belong to the user's organisation.
    503 Service Unavailable
        If WeasyPrint is not installed.
    500 Internal Server Error
        If PDF conversion fails.
    """
    store = _get_report_or_404(report_id)
    # Enforce tenant check
    await project_store.get_or_404(store["project_id"], organisation_id=user.organisation_id)

    if store.get("pdf") is None:
        # Generate on demand
        try:
            pdf_bytes = _pdf_engine.export(store["html"])
            store["pdf"] = pdf_bytes
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail="PDF export requires WeasyPrint. Install with: pip install weasyprint",
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500, detail=f"PDF generation failed: {exc}"
            ) from exc

    project_ref = store.get("project_id", report_id).replace(" ", "_")
    filename = f"{project_ref}_{report_id}.pdf"

    return Response(
        content=store["pdf"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{report_id}/status")
async def report_status(
    report_id: str,
    user: User = Depends(current_active_user),
) -> dict:
    """
    Return generation status for a given report.

    Parameters
    ----------
    report_id : str
        The report ID to check.
    user : User
        The authenticated current user.

    Returns
    -------
    dict
        ``{report_id, status, generated_at, has_pdf, member_count}``.

    Raises
    ------
    404 Not Found
        If the report ID does not exist, or if the associated project
        does not belong to the user's organisation.
    """
    store = _get_report_or_404(report_id)
    # Enforce tenant check
    await project_store.get_or_404(store["project_id"], organisation_id=user.organisation_id)
    return {
        "report_id": report_id,
        "status": "pdf_ready" if store.get("pdf") else "html_ready",
        "generated_at": store.get("generated_at"),
        "has_pdf": store.get("pdf") is not None,
        "member_count": store.get("member_count", 0),
        "report_type": store.get("report_type"),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_and_store_report(
    *,
    project_id: str,
    project_meta: "ProjectMeta",
    members: list[dict[str, Any]],
    report_type: str,
    member_ids: Any,
    fmt: str,
    background_tasks: BackgroundTasks,
) -> "GenerateReportResponse":
    """
    Normalise members, run the reporting modules, render HTML, store the result
    and (optionally) queue PDF generation. Shared by both report endpoints.
    """
    report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"
    logger.info("Generating report %s for project %s.", report_id, project_id)

    # 1. Filter members by member_ids
    if member_ids != "all" and isinstance(member_ids, list):
        id_set = set(member_ids)
        members = [m for m in members if m.get("member_id") in id_set]

    # 2. Normalise
    try:
        rdm = _normalizer.normalize(project_meta=project_meta.model_dump(), members=members)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 3. Run modules
    try:
        rebar_schedule = _rebar_engine.build(rdm)
        quantities = _qty_engine.build(rdm, rebar_schedule)
        compliance = _compliance_engine.build(rdm)
        summary = _summary_engine.build(rdm, quantities, compliance)
    except Exception as exc:
        logger.exception("Module execution failed for report %s.", report_id)
        raise HTTPException(status_code=500, detail=f"Reporting module error: {exc}") from exc

    # 4. Render HTML
    try:
        html = _render_report(
            report_type=report_type, rdm=rdm, rebar_schedule=rebar_schedule,
            quantities=quantities, compliance=compliance, summary=summary,
        )
    except Exception as exc:
        logger.exception("Template rendering failed for report %s.", report_id)
        raise HTTPException(status_code=500, detail=f"Template rendering error: {exc}") from exc

    # 5. Store
    _report_store[report_id] = {
        "report_id": report_id,
        "project_id": project_id,
        "html": html,
        "pdf": None,  # generated on demand at /download
        "report_type": report_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "member_count": len(rdm.members),
        "format": fmt,
        "rdm": rdm,
        "rebar_schedule": rebar_schedule,
        "quantities": quantities,
        "compliance": compliance,
        "summary": summary,
    }

    # 6. Pre-generate PDF in background if requested
    if fmt == "pdf":
        background_tasks.add_task(_generate_pdf_background, report_id, html)

    return GenerateReportResponse(
        report_id=report_id,
        preview_url=f"/api/v1/reports/{report_id}/preview",
        download_url=f"/api/v1/reports/{report_id}/download",
        status="ready" if fmt == "html" else "generating_pdf",
        generated_at=_report_store[report_id]["generated_at"],
        member_count=len(rdm.members),
    )


def _assemble_members_from_stores(project_id: str, design_code: str) -> list[dict[str, Any]]:
    """
    Build the per-member report payload from the project's stored stage results.

    Joins the loading, analysis and design outputs by ``member_id`` into the
    shape required by the report normaliser (``loading_output``,
    ``analysis_output``, ``design_output`` per member).
    """
    from services.loading import loading_service
    from services.analysis import analysis_service
    from services.design import design_service

    def _members_of(payload: Any) -> list[dict[str, Any]]:
        return payload.get("members", []) if isinstance(payload, dict) else []

    def _safe(fn) -> Any:
        try:
            return fn()
        except (KeyError, ValueError):
            return None

    loading = _members_of(_safe(lambda: loading_service.get_output(project_id)))
    analysis = _members_of(_safe(lambda: analysis_service.get_results(project_id)))
    design = _members_of(_safe(lambda: design_service.get_results(project_id)))

    load_by_id = {m.get("member_id"): m for m in loading}
    ana_by_id = {m.get("member_id"): m for m in analysis}

    assembled: list[dict[str, Any]] = []
    for dm in design:
        mid = dm.get("member_id")
        if dm.get("status") in ("skipped", "error"):
            continue
        assembled.append({
            "member_id": mid,
            "member_type": dm.get("member_type", "beam"),
            "floor_level": dm.get("floor_level") or dm.get("storey") or "L01",
            "design_code": dm.get("design_code", design_code),
            "loading_output": load_by_id.get(mid, {}),
            "analysis_output": ana_by_id.get(mid, {}),
            "design_output": dm,
        })
    return assembled


def _get_report_or_404(report_id: str) -> dict:
    """Return the store entry or raise 404."""
    store = _report_store.get(report_id)
    if store is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report '{report_id}' not found. Generate it first via POST /reports/generate.",
        )
    return store


def _render_report(
    report_type: str,
    rdm: Any,
    rebar_schedule: dict,
    quantities: dict,
    compliance: dict,
    summary: dict,
) -> str:
    """
    Dispatch HTML rendering based on report_type.

    Parameters
    ----------
    report_type : str
        One of: calculation_sheets, schedule, quantities, compliance, summary, full.
    rdm : ReportDataModel
    rebar_schedule : dict
    quantities : dict
    compliance : dict
    summary : dict

    Returns
    -------
    str
        Complete HTML document string.
    """
    if report_type == "calculation_sheets":
        return _render_calc_sheets(rdm)

    if report_type == "schedule":
        ctx = {**rebar_schedule, "project": rdm.project}
        return _renderer.render_schedule(ctx)

    if report_type == "quantities":
        ctx = {**quantities, "project": rdm.project}
        return _renderer.render_quantities(ctx)

    if report_type == "compliance":
        return _renderer.render_compliance(compliance)

    if report_type == "summary":
        return _renderer.render_summary(summary)

    # "full" — all pages combined
    member_html_list = []
    for member in rdm.members:
        ctx = _calc_engine.build(rdm.project, member)
        member_html_list.append(_renderer.render_member(member.member_type, ctx))

    schedule_ctx = {**rebar_schedule, "project": rdm.project}
    quantities_ctx = {**quantities, "project": rdm.project}

    combined_ctx = {
        "project": rdm.project,
        "summary_html": _renderer.render_summary(summary),
        "compliance_html": _renderer.render_compliance(compliance),
        "member_html_list": member_html_list,
        "schedule_html": _renderer.render_schedule(schedule_ctx),
        "quantities_html": _renderer.render_quantities(quantities_ctx),
    }
    return _renderer.render_full_report(combined_ctx)


def _render_calc_sheets(rdm: Any) -> str:
    """Render all member calc sheets concatenated in a single HTML body."""
    pages = []
    for member in rdm.members:
        ctx = _calc_engine.build(rdm.project, member)
        pages.append(_renderer.render_member(member.member_type, ctx))
    return "\n".join(pages)


async def _generate_pdf_background(report_id: str, html: str) -> None:
    """Background task: generate and cache PDF for a report."""
    try:
        store = _report_store.get(report_id)
        if store:
            pdf_bytes = _pdf_engine.export(html)
            store["pdf"] = pdf_bytes
            logger.info("Background PDF generated for report %s (%d bytes).", report_id, len(pdf_bytes))
    except Exception as exc:
        logger.warning("Background PDF failed for report %s: %s", report_id, exc)
