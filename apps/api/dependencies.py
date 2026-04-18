"""
dependencies.py
===============
Shared FastAPI dependency functions injected into route handlers.

All gate-enforcement logic lives here — routers call these as ``Depends()``
arguments rather than embedding gate checks in handler bodies.  This enforces
**Rule 2** from the architecture spec: "Gates are enforced at the router level."

Available dependencies
----------------------
get_project          : Returns project or raises 404.
require_file_uploaded       : ProjectStatus >= FILE_UPLOADED
require_geometry_verified   : ProjectStatus >= GEOMETRY_VERIFIED
require_loading_defined     : ProjectStatus >= LOADING_DEFINED
require_analysis_complete   : ProjectStatus >= ANALYSIS_COMPLETE
require_design_complete     : ProjectStatus >= DESIGN_COMPLETE
"""

from __future__ import annotations

from fastapi import status as http_status

from middleware.error_handler import StructuralError
from schemas.project import ProjectResponse, ProjectStatus
from storage.project_store import project_store


def get_project(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: resolve and return a project entity.

    Parameters
    ----------
    project_id : str
        Path parameter injected by FastAPI from the URL.

    Returns
    -------
    ProjectResponse
        The resolved project.

    Raises
    ------
    StructuralError
        HTTP 404 ``PROJECT_NOT_FOUND`` if the project does not exist.
    """
    return project_store.get_or_404(project_id)


def _require_status(project_id: str, required: ProjectStatus, stage_label: str) -> ProjectResponse:
    """
    Internal helper: assert that a project has reached at least ``required`` status.

    Parameters
    ----------
    project_id : str
        Project identifier.
    required : ProjectStatus
        Minimum pipeline stage the project must be at.
    stage_label : str
        Human-readable label for use in the error message.

    Returns
    -------
    ProjectResponse
        The resolved project if the gate is open.

    Raises
    ------
    StructuralError
        HTTP 403 ``GATE_NOT_PASSED`` if the project has not yet reached ``required``.
    """
    project = project_store.get_or_404(project_id)
    current = project_store.get_status(project_id)
    if current is None or current < required:
        raise StructuralError(
            "GATE_NOT_PASSED",
            stage=stage_label,
            details={
                "required_stage": required.label(),
                "current_stage": current.label() if current is not None else "unknown",
            },
            status_code=http_status.HTTP_403_FORBIDDEN,
        )
    return project


def require_file_uploaded(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: project must have a file uploaded.

    Parameters
    ----------
    project_id : str
        Path parameter.

    Returns
    -------
    ProjectResponse
    """
    return _require_status(project_id, ProjectStatus.FILE_UPLOADED, "file_upload")


def require_geometry_verified(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: geometry must have been human-verified (Safety Gate 1).

    Parameters
    ----------
    project_id : str
        Path parameter.

    Returns
    -------
    ProjectResponse
    """
    return _require_status(project_id, ProjectStatus.GEOMETRY_VERIFIED, "geometry_verification")


def require_loading_defined(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: load definitions must have been submitted.

    Parameters
    ----------
    project_id : str
        Path parameter.

    Returns
    -------
    ProjectResponse
    """
    return _require_status(project_id, ProjectStatus.LOADING_DEFINED, "loading_definition")


def require_analysis_complete(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: analysis must be complete before design can run.

    Parameters
    ----------
    project_id : str
        Path parameter.

    Returns
    -------
    ProjectResponse
    """
    return _require_status(project_id, ProjectStatus.ANALYSIS_COMPLETE, "analysis")


def require_design_complete(project_id: str) -> ProjectResponse:
    """
    FastAPI dependency: design must be complete before reports can be generated.

    Parameters
    ----------
    project_id : str
        Path parameter.

    Returns
    -------
    ProjectResponse
    """
    return _require_status(project_id, ProjectStatus.DESIGN_COMPLETE, "design")
