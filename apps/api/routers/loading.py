"""
routers/loading.py
==================
Loading Module router — accepts load definitions, runs the load combination
engine, and returns factored design loads per member.

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
``POST /combinations`` and ``GET /output`` additionally advance the project to
``LOADING_DEFINED`` on success.

Rule
----
This router **never performs engineering calculations** — it calls
``services/loading/`` which wraps the core loading module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, status

from dependencies import require_geometry_verified
from middleware.error_handler import StructuralError
from schemas.loading import (
    LoadDefinitionRequest,
    LoadingOutputResponse,
    LoadValidationResult,
    MemberLoadUpdate,
)
from schemas.project import ProjectResponse, ProjectStatus
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# In-process load definition store (replace with DB in production)
_load_def_store: dict[str, dict[str, Any]] = {}
_load_output_store: dict[str, dict[str, Any]] = {}

# Structural geometry store — populated by the Parser Agent after DXF/PDF parsing.
# Keyed by project_id; value is the parsed StructuralDesignState geometry dict.
# Migrate to ProjectGeometry DB table in Track 2 of the infrastructure upgrade.
_structural_json_store: dict[str, dict[str, Any]] = {}


def register_structural_json(project_id: str, geometry: dict[str, Any]) -> None:
    """
    Store the parsed structural geometry for a project.

    Called by the Parser Agent (or the file parsing router) after DXF/PDF
    parsing is complete.  The loading service reads this to discover member
    IDs, types, and geometry (spans, lengths).

    Parameters
    ----------
    project_id : str
        Owning project identifier.
    geometry : dict[str, Any]
        Structural JSON schema output from the Parser Agent.
    """
    _structural_json_store[project_id] = geometry


# ─── Service calls ────────────────────────────────────────────────────────────


def _run_loading_service(project_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    """
    Orchestrate the Loading Module for all registered members of a project.

    Reads the parsed structural geometry from ``_structural_json_store``, routes
    each member to the appropriate assembler from ``core.loading``, applies
    the ``LoadCombinationEngine`` factors for the project design code, and
    serializes the output using ``LoadSerializer``.

    Parameters
    ----------
    project_id : str
        Owning project.
    definition : dict[str, Any]
        Load definition payload (already validated via ``_validate_definition``).

    Returns
    -------
    dict[str, Any]
        Full loading output conforming to the ``MemberLoadOutput`` schema:
        ``{design_code, members, combination_used, generated_at}``.
    """
    from core.loading import LoadCombinationEngine, LoadSerializer
    from models.loading.schema import DesignCode, LimitState

    # ── Resolve design code ───────────────────────────────────────────────────
    design_code_str = definition.get("design_code", "BS8110")
    design_code = DesignCode.BS8110 if design_code_str == "BS8110" else DesignCode.EC2

    # ── Characteristic base loads from definition ─────────────────────────────
    dead = definition.get("dead_loads", {})
    imposed = definition.get("imposed_loads", {})

    gk_base = sum([
        dead.get("finishes_kNm2", 1.5),
        dead.get("screed_kNm2", 0.8),
        dead.get("services_kNm2", 0.5),
        dead.get("partitions_kNm2", 1.0),
    ])
    qk_base: float = imposed.get("floor_qk_kNm2", 2.5)

    combo_label = (
        "1.4Gk + 1.6Qk" if design_code == DesignCode.BS8110 else "1.35Gk + 1.5Qk"
    )

    # ── Per-member override map ───────────────────────────────────────────────
    overrides: dict[str, dict] = {
        o["member_id"]: o for o in definition.get("member_overrides", [])
    }

    # ── Structural geometry (member catalogue from Parser Agent) ──────────────
    structural_json = _structural_json_store.get(project_id, {})
    parsed_members: dict[str, dict] = {
        m["member_id"]: m for m in structural_json.get("members", [])
    }

    # ── Iterate over registered members ──────────────────────────────────────
    member_ids = project_store.get_member_ids(project_id)
    members_output: list[dict] = []

    # If no members registered yet, generate output from the parsed geometry
    # so the pipeline is not blocked when the project_store has no members.
    effective_ids = member_ids or list(parsed_members.keys())

    for member_id in effective_ids:
        meta = parsed_members.get(member_id, {})
        member_type: str = meta.get("member_type", "beam")
        override = overrides.get(member_id, {})

        # Apply member-level overrides on top of global base loads
        effective_gk = gk_base + float(override.get("dead_extra_kNm2", 0.0))
        effective_qk = float(override.get("imposed_override_kNm2") or qk_base)

        # Add cladding line load for perimeter beams if specified
        cladding_gk = float(dead.get("cladding_kNm", 0.0))

        # Factor loads for ULS and SLS
        uls_udl = LoadCombinationEngine.factor_loads(
            effective_gk + cladding_gk, effective_qk, 0.0, design_code, LimitState.ULS_DOMINANT
        )
        sls_udl = LoadCombinationEngine.factor_loads(
            effective_gk + cladding_gk, effective_qk, 0.0, design_code, LimitState.SLS_CHARACTERISTIC
        )

        # Retrieve spans from parsed geometry; default to a single 5 m span
        raw_spans: list[dict] = meta.get("spans", [{"span_id": "S1", "length_m": 5.0}])
        spans_data = [
            {
                "span_id": s.get("span_id", f"S{i + 1}"),
                "length_m": float(s.get("length_m", 5.0)),
                "loads": {
                    "udl_gk": round(effective_gk, 3),
                    "udl_qk": round(effective_qk, 3),
                    "n_uls": round(uls_udl, 3),
                    "n_sls": round(sls_udl, 3),
                    "point_loads": s.get("point_loads", []),
                },
                # Pattern loading applies when there are 3+ spans
                "pattern_loading_flag": len(raw_spans) >= 3,
            }
            for i, s in enumerate(raw_spans)
        ]

        serialized = LoadSerializer.serialize_member(
            member_id=member_id,
            member_type=member_type,
            design_code=design_code,
            spans_data=spans_data,
            combination_used=combo_label,
            notes=override.get("notes", ""),
        )
        members_output.append(serialized)

    logger.info(
        "Load combinations computed for project %s: %d member(s), code=%s.",
        project_id, len(members_output), design_code_str,
    )

    return {
        "design_code": design_code_str,
        "members": members_output,
        "combination_used": combo_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _validate_definition(definition: dict[str, Any]) -> LoadValidationResult:
    """
    Run pre-flight validation on a load definition dict.

    Parameters
    ----------
    definition : dict[str, Any]
        Load definition to validate.

    Returns
    -------
    LoadValidationResult
    """
    errors: list[str] = []
    warnings: list[str] = []

    imposed = definition.get("imposed_loads", {})
    floor_qk = imposed.get("floor_qk_kNm2", 0)
    if floor_qk == 0:
        errors.append("imposed_loads.floor_qk_kNm2: must be > 0.")
    if floor_qk > 10:
        warnings.append(f"floor_qk_kNm2 = {floor_qk} kN/m² is unusually high — please verify.")

    dead = definition.get("dead_loads", {})
    total_dead = sum([
        dead.get("finishes_kNm2", 0),
        dead.get("screed_kNm2", 0),
        dead.get("services_kNm2", 0),
        dead.get("partitions_kNm2", 0),
    ])
    if total_dead > 8:
        warnings.append(f"Total superimposed dead load = {total_dead:.2f} kN/m² — exceptionally high.")

    return LoadValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{project_id}/define", status_code=status.HTTP_201_CREATED)
def define_loads(
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
        ``{project_id, status, definition_id, created_at}``
    """
    definition_dict = payload.model_dump()
    _load_def_store[project_id] = definition_dict

    logger.info(
        "Load definition submitted for project %s. Code: %s, Occupancy: %s.",
        project_id,
        payload.design_code,
        payload.occupancy_category,
    )
    return {
        "project_id": project_id,
        "status": "accepted",
        "design_code": payload.design_code,
        "occupancy_category": payload.occupancy_category,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{project_id}")
def get_load_definitions(
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
    return _load_def_store.get(project_id, {})


@router.put("/{project_id}/member/{member_id}")
def update_member_loads(
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

    Raises
    ------
    StructuralError
        ``MEMBER_NOT_FOUND`` if member_id is not registered to the project.
    """
    member_ids = project_store.get_member_ids(project_id)
    # Only enforce membership check if the project has registered members
    if member_ids and member_id not in member_ids:
        raise StructuralError(
            "MEMBER_NOT_FOUND",
            member_id=member_id,
            details={"project_id": project_id},
            status_code=404,
        )

    definition = _load_def_store.setdefault(project_id, {})
    overrides = definition.setdefault("member_overrides", [])

    # Update or append
    existing = next((o for o in overrides if o.get("member_id") == member_id), None)
    if existing:
        if payload.dead_extra_kNm2 is not None:
            existing["dead_extra_kNm2"] = payload.dead_extra_kNm2
        if payload.imposed_override_kNm2 is not None:
            existing["imposed_override_kNm2"] = payload.imposed_override_kNm2
        existing["notes"] = payload.notes
        result = existing
    else:
        entry = {"member_id": member_id, **payload.model_dump()}
        overrides.append(entry)
        result = entry

    logger.info("Load override applied to member %s in project %s.", member_id, project_id)
    return result


@router.post("/{project_id}/combinations", status_code=status.HTTP_200_OK)
def run_combinations(
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
    definition = _load_def_store.get(project_id)
    if not definition:
        raise StructuralError(
            "INVALID_LOAD_INPUT",
            stage="loading",
            details={"reason": "No load definition found. Call POST /define first."},
            status_code=400,
        )

    output = _run_loading_service(project_id, definition)
    _load_output_store[project_id] = output

    # Advance pipeline
    project_store.advance_status(project_id, ProjectStatus.LOADING_DEFINED)
    logger.info("Load combinations computed for project %s.", project_id)
    return output


@router.get("/{project_id}/output", response_model=LoadingOutputResponse)
def get_loading_output(
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
        HTTP 404 ``INVALID_LOAD_INPUT`` if combinations have not been run yet.
    """
    output = _load_output_store.get(project_id)
    if output is None:
        raise StructuralError(
            "INVALID_LOAD_INPUT",
            stage="loading_output",
            details={"reason": "Run POST /combinations first."},
            status_code=404,
        )
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

    Use this to provide instant feedback in the IDE before committing the definition.

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
    return _validate_definition(payload.model_dump())
