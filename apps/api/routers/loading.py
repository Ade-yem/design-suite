"""
routers/loading.py
==================
Loading Module router — thin HTTP wrapper around ``services.loading``.

Endpoints
---------
POST   /api/v1/loading/{project_id}/define        Define loads for the project
GET    /api/v1/loading/{project_id}               Get current load definitions
PUT    /api/v1/loading/{project_id}/member/{id}   Update loads for a specific member
POST   /api/v1/loading/{project_id}/combinations  Run load combination engine
GET    /api/v1/loading/{project_id}/output        Get full loading output JSON
POST   /api/v1/loading/{project_id}/validate      Validate load definitions

Gate enforcement
----------------
All endpoints require ``GEOMETRY_VERIFIED`` status (Safety Gate 1 must be open).

Rule
----
This router **never performs engineering calculations** — all logic lives in
``services.loading.LoadingService``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from dependencies import require_geometry_verified
from middleware.error_handler import StructuralError
from schemas.loading import (
    LoadDefinitionRequest,
    LoadingOutputResponse,
    LoadValidationResult,
    MemberLoadUpdate,
)
from schemas.project import ProjectResponse
from services.loading import loading_service

logger = logging.getLogger(__name__)
router = APIRouter()





# ─── Endpoints ────────────────────────────────────────────────────────────────


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{project_id}/define", status_code=status.HTTP_201_CREATED)
async def define_loads(
    project_id: str,
    payload: LoadDefinitionRequest,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> dict:
    """
    Submit load definitions for a project.

    The definition is validated and stored.  It does not automatically run the
    combination engine — call ``POST /combinations`` for that.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : LoadDefinitionRequest
        Complete load definition.
    project : ProjectResponse
        Gate dependency — ``GEOMETRY_VERIFIED`` required.

    Returns
    -------
    dict
        ``{project_id, status, design_code, occupancy_category, created_at}``
    """
    return await loading_service.define(project_id, payload.model_dump())


@router.get("/{project_id}")
async def get_load_definitions(
    project_id: str,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> dict:
    """
    Return the current load definitions for a project.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    dict
        Stored load definition dict, or empty if not yet defined.
    """
    await loading_service.ensure_cached(project_id)
    return loading_service.get_definition(project_id)


@router.put("/{project_id}/member/{member_id}")
async def update_member_loads(
    project_id: str,
    member_id: str,
    payload: MemberLoadUpdate,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> dict:
    """
    Apply per-member load overrides to the stored definition.

    Parameters
    ----------
    project_id : str
        Target project.
    member_id : str
        Member identifier to update.
    payload : MemberLoadUpdate
        Load update values.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    dict
        Updated override record.
    """
    return await loading_service.update_member_loads(
        project_id,
        member_id,
        dead_extra_kNm2=payload.dead_extra_kNm2,
        imposed_override_kNm2=payload.imposed_override_kNm2,
        notes=payload.notes or "",
    )


@router.post("/{project_id}/combinations", status_code=status.HTTP_200_OK)
async def run_combinations(
    project_id: str,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> dict:
    """
    Run the load combination engine and produce factored design loads for all members.

    Calling this endpoint advances the project to ``LOADING_DEFINED`` status.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    dict
        Full loading output with factored ULS and SLS loads per member.

    Raises
    ------
    StructuralError
        ``INVALID_LOAD_INPUT`` if no load definition has been submitted.
    """
    try:
        return await loading_service.run_combinations(project_id)
    except ValueError as exc:
        raise StructuralError(
            "INVALID_LOAD_INPUT",
            stage="loading",
            details={"reason": str(exc)},
            status_code=400,
        ) from exc


@router.get("/{project_id}/output", response_model=LoadingOutputResponse)
async def get_loading_output(
    project_id: str,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> LoadingOutputResponse:
    """
    Return the full loading output JSON produced by the combination engine.

    Parameters
    ----------
    project_id : str
        Target project.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    LoadingOutputResponse

    Raises
    ------
    StructuralError
        HTTP 404 if combinations have not been run yet.
    """
    await loading_service.ensure_cached(project_id)
    try:
        output = loading_service.get_output(project_id)
    except KeyError as exc:
        raise StructuralError(
            "INVALID_LOAD_INPUT",
            stage="loading_output",
            details={"reason": str(exc)},
            status_code=404,
        ) from exc
    return LoadingOutputResponse(
        project_id=project_id,
        design_code=output.get("design_code", ""),
        members=output.get("members", []),
        generated_at=output.get("generated_at", ""),
    )


@router.post("/{project_id}/validate", response_model=LoadValidationResult)
def validate_loads(
    project_id: str,
    payload: LoadDefinitionRequest,
    project: ProjectResponse = Depends(require_geometry_verified),
) -> LoadValidationResult:
    """
    Validate a load definition without persisting it.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : LoadDefinitionRequest
        Load definition to validate.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    LoadValidationResult
        ``{valid, errors, warnings}``
    """
    return loading_service.validate(payload.model_dump())
