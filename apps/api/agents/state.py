"""
services/agents/state.py
========================
Canonical graph state for the Structural Design Copilot LangGraph pipeline.

This is the **single most important object in the orchestration layer** — every
node reads from it and writes to it.  It is the shared memory of the entire
pipeline run.  LangGraph passes an immutable snapshot of this state to each
node; nodes return a partial dict of *only the fields they mutate*.

Design rules
------------
- ``messages`` and ``agent_logs`` use ``Annotated[list, add]`` so that
  LangGraph **appends** each node's additions rather than replacing the list.
- All other fields are plain Python types — nodes overwrite them directly.
- ``None`` is the zero-value for optional fields; empty list ``[]`` for
  collections.  Do not use sentinel strings — the router logic uses ``is None``
  checks exclusively.

Units convention (mirrors FastAPI schema convention)
----------------------------------------------------
- Forces  : kN
- Moments : kNm
- Lengths : m  (except section dimensions which are mm)
- Stresses: MPa
- Areas   : mm²
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Optional

from typing_extensions import TypedDict


class StructuralDesignState(TypedDict, total=False):
    """
    Shared state object threaded through every node in the StateGraph.

    All fields are optional at the TypedDict level (``total=False``) because
    LangGraph nodes return *partial* state updates — a node that only touches
    loading fields must not be required to re-supply geometry fields.

    Sections
    --------
    1. Project context
    2. Conversation / logs  (append-only via Annotated[list, add])
    3. File & geometry
    4. Loading
    5. Analysis
    6. Design
    7. Iteration tracking
    8. Drafting
    9. Reporting
    10. Error handling
    """

    # ── 1. Project context ────────────────────────────────────────────────────

    project_id: str
    """UUID of the active project (must be created via POST /api/v1/projects/)."""

    design_code: str
    """Primary design code: ``"BS8110"`` or ``"EC2"``."""

    pipeline_status: str
    """
    Current pipeline stage label — mirrors the FastAPI ``ProjectStatus`` enum.
    Values: created | file_uploaded | geometry_verified | loading_defined |
            analysis_complete | design_complete | report_generated.
    """

    # ── 2. Conversation history (append-only) ─────────────────────────────────

    messages: Annotated[list, add]
    """
    Full LangChain message history for the IDE left-panel chat.
    Each node appends ``AIMessage`` or ``HumanMessage`` objects.
    LangGraph merges via ``add`` — never replaced, only extended.
    """

    agent_logs: Annotated[list, add]
    """
    Structured status log entries for the IDE left-panel status stream.
    Each entry is a ``dict`` with keys: agent, status, timestamp, detail.
    """

    # ── 3. File & geometry ────────────────────────────────────────────────────

    uploaded_file_path: Optional[str]
    """Filesystem path to the uploaded DXF or PDF file."""

    parse_job_id: Optional[str]
    """Job ID for the async parsing task (poll via GET /api/v1/jobs/{job_id})."""

    parsed_structural_json: Optional[dict]
    """
    Parsed geometry dict returned by the Vision Agent / ezdxf pipeline.
    Schema: {members: [], scale: {factor, unit}, raw_entity_count, parse_warnings}.
    """

    geometry_verified: bool
    """True once the engineer has confirmed parsed geometry (Gate 1)."""

    unit_confirmation: Optional[dict]
    """
    Unit and scale detection result.
    Schema: {ambiguous: bool, detected_unit: str, confidence: str,
             sample_dimensions: list[float]}.
    """

    geometry_corrections: list
    """List of member-level corrections applied by the engineer at Gate 1."""

    # ── 4. Loading ────────────────────────────────────────────────────────────

    load_definition: Optional[dict]
    """
    Validated load definition payload matching ``LoadDefinitionRequest`` schema.
    None until the Analyst Agent has collected all required inputs.
    """

    loading_output: Optional[dict]
    """Full factored loading output (member ULS/SLS loads) from the loading engine."""

    loading_confirmed: bool
    """True once the engineer has confirmed the assembled loads (Gate 2)."""

    # ── 5. Analysis ───────────────────────────────────────────────────────────

    analysis_results: Optional[dict]
    """Full AnalysisOutputSchema dict from the analysis engine."""

    analysis_job_id: Optional[str]
    """Job ID for the async analysis run."""

    analysis_complete: bool
    """True once analysis has successfully completed for all target members."""

    failed_members_analysis: list
    """Member IDs that returned errors or warnings from the analysis engine."""

    # ── 6. Design ─────────────────────────────────────────────────────────────

    design_results: Optional[dict]
    """Full design suite output dict (member reinforcement schedules)."""

    design_job_id: Optional[str]
    """Job ID for the async design run."""

    design_complete: bool
    """True once the design suite has successfully designed all target members."""

    failed_members_design: list
    """
    Member IDs that failed limit state checks in the design suite.
    Non-empty triggers the Designer → Analyst re-analysis feedback loop.
    """

    design_confirmed: bool
    """True once the engineer has reviewed and confirmed the design schedule (Gate 3)."""

    # ── 7. Iteration tracking ─────────────────────────────────────────────────

    iteration_count: int
    """Number of completed self-weight convergence iterations."""

    reanalysis_triggered: bool
    """
    True when the Designer detects a self-weight change >5% and sends
    failed members back to the Analyst for re-analysis.
    """

    # ── 8. Drafting ───────────────────────────────────────────────────────────

    drawing_commands: Optional[list]
    """
    List of per-member drawing command sets.  Each entry:
    {member_id, member_type, section: [...], elevation: [...],
     dimensions: [...], bar_marks: [...], annotations: [...]}.
    """

    layer_package: Optional[dict]
    """
    Layer structure for the Canvas panel layer manager.
    {layers: [{id, label, member_type, visible, color}], bounds: {w, h}}.
    """

    drawing_confirmed: bool
    """True once the engineer has reviewed and confirmed all drawings (Gate 4)."""

    updated_drawing: Optional[dict]
    """
    Single-member drawing update after a canvas edit is validated.
    {member_id: str, commands: {...}}.  Sent to the frontend as a
    partial canvas refresh rather than a full redraw.
    """

    revert_drawing: Optional[str]
    """
    Member ID whose drawing the frontend must revert because a canvas
    edit failed limit state checks.
    """

    # ── 9. Reporting ──────────────────────────────────────────────────────────

    report_id: Optional[str]
    """Report ID returned by POST /api/v1/reports/generate."""

    report_complete: bool
    """True once the final report has been successfully generated."""

    # ── 10. Error handling ────────────────────────────────────────────────────

    current_error: Optional[str]
    """
    Error code from ``config.ERROR_CODES`` describing the most recent
    failure.  Cleared when the error is resolved.
    """

    retry_count: int
    """Number of consecutive retries for the current failing operation."""


# ── State factory ─────────────────────────────────────────────────────────────


def initial_state(project_id: str, design_code: str = "BS8110") -> StructuralDesignState:
    """
    Return a fully initialised state dict with safe zero values for all fields.

    Parameters
    ----------
    project_id : str
        Project identifier (must already exist in the project store).
    design_code : str
        Primary design code — ``"BS8110"`` or ``"EC2"``.

    Returns
    -------
    StructuralDesignState
        Ready-to-use state for ``graph.invoke()``.
    """
    return StructuralDesignState(
        project_id=project_id,
        design_code=design_code,
        pipeline_status="created",
        messages=[],
        agent_logs=[],
        uploaded_file_path=None,
        parse_job_id=None,
        parsed_structural_json=None,
        geometry_verified=False,
        unit_confirmation=None,
        geometry_corrections=[],
        load_definition=None,
        loading_output=None,
        loading_confirmed=False,
        analysis_results=None,
        analysis_job_id=None,
        analysis_complete=False,
        failed_members_analysis=[],
        design_results=None,
        design_job_id=None,
        design_complete=False,
        failed_members_design=[],
        design_confirmed=False,
        iteration_count=0,
        reanalysis_triggered=False,
        drawing_commands=None,
        layer_package=None,
        drawing_confirmed=False,
        updated_drawing=None,
        revert_drawing=None,
        report_id=None,
        report_complete=False,
        current_error=None,
        retry_count=0,
    )
