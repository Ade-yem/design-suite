"""
services/agents/analyst.py  (Analyst Agent)
============================================
Analyst Agent node — the "Global Physics" of the pipeline.

Responsibilities
----------------
1. Gather *design considerations* conversationally once geometry is confirmed:
   building type / purpose, whether it is multi-storey and how many storeys,
   typical storey height, and any known dead loads / soil / material context.
   This qualitative project profile is what governs the loading.
2. Reason from those considerations to code-compliant load parameters —
   in particular, derive the characteristic imposed load Qk from the building's
   occupancy via the standard occupancy table rather than asking for it directly.
   Uses the LLM to extract structured data from natural language; never invents
   required values — asks for missing fields.
3. Validate the resulting load definition via the loading service before submit.
4. Run load combinations and trigger the analysis engine.
5. Stream live progress to the IDE left-panel status log.
6. Handle the re-analysis loop when the Designer sends back failed members
   due to self-weight changes.
7. Present analysis results with a clear narrative summary.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.state import StructuralDesignState
from config import settings


logger = logging.getLogger(__name__)


def _get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-pro",
        temperature=0,
        google_api_key=settings.GEMINI_API_KEY,
    )

# Design-consideration fields required before loads can be assembled.
# (Building occupancy governs Qk; storey count governs load take-down.)
_REQUIRED_CONSIDERATION_FIELDS: list[str] = [
    "occupancy_category",
    "num_storeys",
]

# Dead-load component keys carried from the discovery dialogue into the
# load definition (the loading engine supplies its own defaults for any absent).
_DEAD_LOAD_KEYS: tuple[str, ...] = (
    "finishes_kNm2", "screed_kNm2", "services_kNm2", "partitions_kNm2", "cladding_kNm",
)

# Maximum self-weight convergence iterations before issuing a warning
_MAX_ITERATIONS = 5


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_considerations_prompt(design_code: str) -> str:
    """
    Opening question that kicks off the design-considerations dialogue.

    Asked once, immediately after geometry is confirmed, before any loads are
    assembled.

    Parameters
    ----------
    design_code : str
        Active design code, surfaced so the engineer knows the basis.

    Returns
    -------
    str
        Markdown question for the IDE chat panel.
    """
    return (
        "✅ **Geometry confirmed.** Before I assemble the loads, tell me about the "
        f"project so I can select the right design parameters under **{design_code}**:\n\n"
        "1. **Building type / purpose** — what is it used for? "
        "(e.g. residential, office, retail, school, hospital, car park, warehouse)\n"
        "2. **Is it a multi-storey building?** If so, **how many storeys / floors**?\n"
        "3. **Typical clear storey height** (m)?\n"
        "4. *(Optional)* any known **finishes / superimposed dead loads**, "
        "**soil bearing capacity**, or **concrete grade**.\n\n"
        "Answer in plain English — e.g. "
        "*\"It's a 4-storey office building, 3.2 m clear per floor.\"*"
    )


def _considerations_extraction_prompt(message: str, design_code: str) -> str:
    """
    Build the LLM prompt that maps the engineer's description to parameters.

    Parameters
    ----------
    message : str
        The engineer's natural-language project description.
    design_code : str
        Active design code (already chosen at project creation).

    Returns
    -------
    str
        Extraction prompt instructing the model to extract, never invent.
    """
    return (
        "You are a junior structural engineer extracting a project profile from "
        f"the senior engineer's description. The design code is {design_code}.\n"
        "Return ONLY a valid JSON object. Set any value not explicitly stated or "
        "clearly implied to null — do NOT invent or assume.\n\n"
        "Map the building usage to the closest occupancy_category from this set:\n"
        "  residential | office | retail | roof_accessible | "
        "roof_non_accessible | stairs | custom\n"
        "Guidance: flats/apartments/houses→residential; offices→office; "
        "shops/malls/showrooms→retail; warehouses/storage→custom; "
        "schools/classrooms→office; car parks→custom. Use 'custom' only when "
        "nothing fits, and then also fill imposed_qk_kNm2 if a value is stated.\n\n"
        "Schema fields:\n"
        "  building_type (str, the literal usage e.g. 'office')\n"
        "  building_purpose (str, short description)\n"
        "  occupancy_category (one of the set above)\n"
        "  is_multistorey (bool)\n"
        "  num_storeys (int, number of floor levels)\n"
        "  storey_height_m (float, clear storey height in metres)\n"
        "  is_braced (bool, true unless explicitly an unbraced/sway frame)\n"
        "  imposed_qk_kNm2 (float, only if an explicit imposed load is stated)\n"
        "  bearing_capacity_kPa (float, soil safe bearing capacity if stated)\n"
        "  dead_loads.finishes_kNm2 (float, optional)\n"
        "  dead_loads.screed_kNm2 (float, optional)\n"
        "  dead_loads.services_kNm2 (float, optional)\n"
        "  dead_loads.partitions_kNm2 (float, optional)\n\n"
        f"Description: {message}"
    )


def _extract_missing_consideration_fields(params: dict) -> list[str]:
    """
    Identify required design-consideration fields that are still unknown.

    Single-storey buildings default ``num_storeys`` to 1 (mutating ``params``)
    so the engineer is not asked a storey count that is implied.

    Parameters
    ----------
    params : dict
        Project parameters accumulated so far across dialogue turns.

    Returns
    -------
    list[str]
        Names of the still-missing required fields.
    """
    missing: list[str] = []

    if not params.get("occupancy_category"):
        missing.append("occupancy_category")

    if not params.get("num_storeys"):
        if params.get("is_multistorey") is False:
            params["num_storeys"] = 1
        else:
            missing.append("num_storeys")

    return missing


def _build_missing_consideration_question(missing: list[str]) -> str:
    """
    Build a targeted chat message asking for missing design considerations.

    Parameters
    ----------
    missing : list[str]
        List of missing field names.

    Returns
    -------
    str
        Natural-language follow-up question.
    """
    questions = {
        "occupancy_category": (
            "What is the building used for? "
            "(residential / office / retail / car park / roof, etc.) — "
            "this sets the imposed load."
        ),
        "num_storeys": (
            "Is this a multi-storey building, and if so how many storeys / "
            "floor levels does it have?"
        ),
    }
    asked = [f"- {questions.get(f, f)}" for f in missing]
    return (
        "Thanks — a couple more details before I can assemble the loads:\n\n"
        + "\n".join(asked)
    )


def _build_load_definition_from_parameters(
    params: dict, design_code: str, qk: float
) -> dict:
    """
    Assemble a load definition from gathered considerations and the derived Qk.

    Only dead-load components the engineer actually provided are passed through;
    the loading engine applies its own defaults for anything absent.

    Parameters
    ----------
    params : dict
        Confirmed project parameters.
    design_code : str
        Active design code.
    qk : float
        Characteristic imposed floor load (kN/m²), derived or explicit.

    Returns
    -------
    dict
        Payload matching ``LoadDefinitionRequest`` shape.
    """
    dead = params.get("dead_loads") or {}
    dead_loads = {k: dead[k] for k in _DEAD_LOAD_KEYS if dead.get(k) is not None}

    load_def: dict[str, Any] = {
        "design_code": design_code,
        "occupancy_category": params.get("occupancy_category", "office"),
        "imposed_loads": {"floor_qk_kNm2": float(qk)},
    }
    if dead_loads:
        load_def["dead_loads"] = dead_loads
    return load_def


def _build_parameters_summary(params: dict, design_code: str, qk: float) -> str:
    """
    Build the human-readable derived-parameters card for engineer confirmation.

    Parameters
    ----------
    params : dict
        Confirmed project parameters.
    design_code : str
        Active design code.
    qk : float
        Derived/explicit characteristic imposed load (kN/m²).

    Returns
    -------
    str
        Markdown summary for the IDE chat panel.
    """
    occupancy = params.get("occupancy_category", "office")
    num_storeys = params.get("num_storeys", 1)
    multistorey = "Yes" if (params.get("is_multistorey") or num_storeys > 1) else "No"
    height = params.get("storey_height_m")
    building = params.get("building_type") or params.get("building_purpose") or "—"

    lines = [
        "### 📋 Derived Project Parameters",
        "",
        f"- **Design code:** {design_code}",
        f"- **Building type / purpose:** {building}",
        f"- **Multi-storey:** {multistorey}  (**{num_storeys}** storey(s))",
    ]
    if height:
        lines.append(f"- **Clear storey height:** {height} m")
    lines.append(
        f"- **Occupancy:** {occupancy} → **Imposed load Qk = {qk:g} kN/m²** "
        "(standard occupancy table)"
    )

    dead = params.get("dead_loads") or {}
    if dead:
        dead_str = ", ".join(f"{k.replace('_kNm2', '')}={v}" for k, v in dead.items())
        lines.append(f"- **Superimposed dead loads:** {dead_str} kN/m²")
    if params.get("bearing_capacity_kPa"):
        lines.append(f"- **Soil bearing capacity:** {params['bearing_capacity_kPa']} kN/m²")

    lines.append("")
    lines.append(
        "I'll assemble the factored loads on this basis and run the analysis. "
        "Confirm the loads to proceed, or tell me what to adjust."
    )
    return "\n".join(lines)


def _build_analysis_narrative(results: dict) -> str:
    """
    Build a readable Markdown summary of analysis results.

    Parameters
    ----------
    results : dict
        ``AnalysisResultsResponse`` dict.

    Returns
    -------
    str
        Markdown summary for the IDE chat panel.
    """
    members = results.get("members", [])
    total = len(members)
    failed = [m["member_id"] for m in members if m.get("status") == "error"]
    passed = total - len(failed)

    lines = [
        f"**Structural Analysis Complete — {total} member(s)**\n",
        f"- ✅ Passed:  {passed}",
        f"- ❌ Errors:  {len(failed)}" if failed else "- ✅ Errors:  0",
    ]
    if failed:
        lines.append(f"\nFailed members: {', '.join(failed)}")

    lines.append(
        "\nResults are available in the Canvas panel. "
        "Confirm loads and **click Confirm Analysis** to proceed to design."
    )
    return "\n".join(lines)


# ─── Node ─────────────────────────────────────────────────────────────────────


async def analyst_node(state: StructuralDesignState) -> dict:
    """
    Analyst Agent LangGraph node.

    Entry conditions:
    - ``geometry_verified = True`` (Gate 1 passed)
    - OR ``reanalysis_triggered = True`` (Designer feedback loop)

    Parameters
    ----------
    state : StructuralDesignState
        Current pipeline state.

    Returns
    -------
    dict
        Partial state update.
    """
    project_id = state["project_id"]
    log_entry = {
        "agent": "analyst",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logs: list[dict] = []

    # ── Re-analysis branch ────────────────────────────────────────────────────
    if state.get("reanalysis_triggered"):
        return await _handle_reanalysis(state, log_entry)

    # ── Design considerations + load collection ───────────────────────────────
    # After geometry confirmation the Analyst first profiles the project
    # (building type, storeys, purpose) and reasons to the load parameters
    # before any combination is assembled.
    if not state.get("load_definition"):
        return await _collect_design_considerations(state, log_entry)

    # ── Run combinations ──────────────────────────────────────────────────────
    try:
        from services.loading import loading_service
        loading_service.run_combinations(project_id)
        logs.append({**log_entry, "status": "combinations_run"})
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Load combinations failed: {exc}")],
            "agent_logs": logs,
            "current_error": "INVALID_LOAD_INPUT",
        }

    # ── Run full analysis ─────────────────────────────────────────────────────
    try:
        from services.analysis import analysis_service
        logs.append({**log_entry, "status": "analysis_started"})

        # Define progress callback
        def _progress(step: str, pct: float) -> None:
            logs.append({
                **log_entry,
                "status": "analysis_running",
                "detail": step,
                "pct": pct,
            })

        await analysis_service.run(
            project_id,
            member_ids=None,
            options={"pattern_loading": True, "self_weight_iteration": True},
            progress_cb=_progress,
        )
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Analysis run failed: {exc}")],
            "agent_logs": logs,
            "current_error": "ANALYSIS_FAILED",
        }

    # ── Fetch results ─────────────────────────────────────────────────────────
    try:
        await analysis_service.ensure_cached(project_id)
        results = analysis_service.get_results(project_id)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Could not retrieve analysis results: {exc}")],
            "agent_logs": logs,
            "current_error": "ANALYSIS_FAILED",
        }

    failed_members = [
        m["member_id"] for m in results.get("members", []) if m.get("status") == "error"
    ]
    narrative = _build_analysis_narrative(results)

    return {
        "analysis_results": results,
        "analysis_complete": True,
        "failed_members_analysis": failed_members,
        "pipeline_status": "analysis_complete",
        "messages": [AIMessage(content=narrative)],
        "agent_logs": logs + [{**log_entry, "status": "complete"}],
        "current_error": None,
    }


async def _collect_design_considerations(
    state: StructuralDesignState, log_entry: dict
) -> dict:
    """
    Run the design-considerations dialogue, then reason to a load definition.

    Flow
    ----
    1. If the engineer has not yet replied to the opening prompt, ask about the
       building type / purpose, storeys and storey height.
    2. LLM-extract a project profile from the reply (extract only, never invent),
       merging with anything gathered on earlier turns.
    3. If required fields (occupancy, storey count) are missing, ask a targeted
       follow-up rather than guessing.
    4. Derive the imposed load Qk from occupancy via the loading service; for a
       ``custom`` occupancy with no stated Qk, ask for it explicitly.
    5. Assemble the load definition, validate (non-blocking), and submit.

    Parameters
    ----------
    state : StructuralDesignState
    log_entry : dict
        Base log entry for this agent invocation.

    Returns
    -------
    dict
        Partial state update.
    """
    from services.loading import loading_service

    messages = state.get("messages", [])
    design_code = state.get("design_code", "BS8110")
    params: dict = dict(state.get("project_parameters") or {})

    last = messages[-1] if messages else None

    # ── Step 1: open the dialogue if the engineer hasn't replied yet ──────────
    if not isinstance(last, HumanMessage):
        return {
            "messages": [AIMessage(content=_build_considerations_prompt(design_code))],
            "agent_logs": [{**log_entry, "status": "awaiting_design_considerations"}],
        }

    # ── Step 2: LLM extraction — extracts only, never invents ─────────────────
    try:
        raw = await _get_llm().ainvoke(
            _considerations_extraction_prompt(last.text, design_code)
        )
        content = raw.text.replace("```json", "").replace("```", "").strip()
        extracted: dict = json.loads(content)
    except Exception:
        extracted = {}

    # Merge new non-null values onto the running profile (dead_loads merged deep).
    for key, value in extracted.items():
        if value is None:
            continue
        if key == "dead_loads" and isinstance(value, dict):
            merged_dead = dict(params.get("dead_loads") or {})
            merged_dead.update({k: v for k, v in value.items() if v is not None})
            params["dead_loads"] = merged_dead
        else:
            params[key] = value

    # ── Step 3: ask for any missing required considerations ───────────────────
    missing = _extract_missing_consideration_fields(params)
    if missing:
        return {
            "project_parameters": params,
            "messages": [AIMessage(content=_build_missing_consideration_question(missing))],
            "agent_logs": [
                {**log_entry, "status": "design_considerations_incomplete", "detail": missing}
            ],
        }

    # ── Step 4: derive the imposed load Qk from occupancy ─────────────────────
    occupancy = params.get("occupancy_category", "office")
    qk = params.get("imposed_qk_kNm2")
    if qk is None:
        qk = loading_service.imposed_load_for(occupancy, design_code)
    if qk is None:
        return {
            "project_parameters": params,
            "messages": [AIMessage(content=(
                "I couldn't map that occupancy to a standard imposed load. "
                "What characteristic imposed floor load Qk (kN/m²) should I use?"
            ))],
            "agent_logs": [{**log_entry, "status": "awaiting_custom_qk"}],
        }

    # ── Step 5: assemble, validate and submit the load definition ─────────────
    load_def = _build_load_definition_from_parameters(params, design_code, float(qk))

    project_id = state["project_id"]
    try:
        validation = loading_service.validate(load_def)
        if not validation.valid:
            errors = validation.errors
            return {
                "project_parameters": params,
                "messages": [AIMessage(content=(
                    "⚠️ Load definition has errors:\n"
                    + "\n".join(f"- {e}" for e in errors)
                    + "\nPlease correct and resubmit."
                ))],
                "agent_logs": [{**log_entry, "status": "validation_failed", "detail": errors}],
            }
    except Exception:
        pass  # Validation failure is non-blocking if the service is unavailable

    await loading_service.define(project_id, load_def)

    return {
        "project_parameters": params,
        "load_definition": load_def,
        "messages": [AIMessage(content=_build_parameters_summary(params, design_code, float(qk)))],
        "agent_logs": [{**log_entry, "status": "design_considerations_complete"}],
    }


async def _handle_reanalysis(
    state: StructuralDesignState, log_entry: dict
) -> dict:
    """
    Re-run analysis for failed members in the Designer → Analyst feedback loop.

    Parameters
    ----------
    state : StructuralDesignState
    log_entry : dict

    Returns
    -------
    dict
        Partial state update.
    """
    project_id = state["project_id"]
    failed = state.get("failed_members_design", [])
    iteration = state.get("iteration_count", 0)

    if iteration >= _MAX_ITERATIONS:
        return {
            "messages": [AIMessage(content=(
                f"⚠️ **Convergence Warning** — {iteration} iterations completed.\n\n"
                f"Members {', '.join(failed)} have not converged. "
                "Please review member sizes or loading manually."
            ))],
            "agent_logs": [{**log_entry, "status": "convergence_failed"}],
            "current_error": "CONVERGENCE_FAILED",
            "reanalysis_triggered": False,
        }

    # Re-run for failed members only
    try:
        from services.analysis import analysis_service
        await analysis_service.run(
            project_id,
            member_ids=failed,
            options={"self_weight_iteration": True},
        )
        await analysis_service.ensure_cached(project_id)
        new_results = analysis_service.get_results(project_id)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Re-analysis failed: {exc}")],
            "agent_logs": [{**log_entry, "status": "reanalysis_failed"}],
            "current_error": "ANALYSIS_FAILED",
        }

    # Merge new results into existing
    existing = state.get("analysis_results") or {"members": []}
    existing_map = {m["member_id"]: m for m in existing.get("members", [])}
    for m in new_results.get("members", []):
        existing_map[m["member_id"]] = m
    merged = {**existing, "members": list(existing_map.values())}

    return {
        "analysis_results": merged,
        "reanalysis_triggered": False,
        "iteration_count": iteration + 1,
        "agent_logs": [{
            **log_entry,
            "status": f"reanalysis_complete_iteration_{iteration + 1}",
        }],
        "messages": [AIMessage(content=(
            f"♻️ Re-analysis complete (iteration {iteration + 1}). "
            "Resuming design…"
        ))],
    }
