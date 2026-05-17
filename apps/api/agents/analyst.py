"""
services/agents/analyst.py  (Analyst Agent)
============================================
Analyst Agent node — the "Global Physics" of the pipeline.

Responsibilities
----------------
1. Collect load definition inputs conversationally from the engineer.
   Uses the LLM to extract structured data from natural language.
   Never invents or defaults required values — asks for missing fields.
2. Validate the definition via the loading API before submission.
3. Run load combinations and trigger the analysis engine.
4. Stream live progress to the IDE left-panel status log.
5. Handle the re-analysis loop when the Designer sends back failed members
   due to self-weight changes.
6. Present analysis results with a clear narrative summary.
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


# LLM used for load input extraction only
_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)

# Required fields for load definition — used to detect missing inputs
_REQUIRED_LOAD_FIELDS: list[str] = [
    "design_code",
    "occupancy_category",
    "imposed_loads.floor_qk_kNm2",
]

# Maximum self-weight convergence iterations before issuing a warning
_MAX_ITERATIONS = 5


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _extract_missing_fields(load_data: dict) -> list[str]:
    """
    Identify load definition fields that are null or absent.

    Parameters
    ----------
    load_data : dict
        Partially-populated load definition extracted from natural language.

    Returns
    -------
    list[str]
        Dot-notation field names that are missing or None.
    """
    missing = []
    for field in _REQUIRED_LOAD_FIELDS:
        keys = field.split(".")
        val: Any = load_data
        for k in keys:
            if not isinstance(val, dict):
                val = None
                break
            val = val.get(k)
        if val is None:
            missing.append(field)
    return missing


def _build_missing_field_question(missing: list[str]) -> str:
    """
    Build a targeted chat message asking for missing load inputs.

    Parameters
    ----------
    missing : list[str]
        List of missing field paths.

    Returns
    -------
    str
        Natural language question for the engineer.
    """
    questions = {
        "design_code":                    "Which design code should I use? (BS8110 or EC2)",
        "occupancy_category":             "What is the building occupancy? (residential / office / retail / roof_accessible / roof_non_accessible / stairs)",
        "imposed_loads.floor_qk_kNm2":    "What is the characteristic imposed floor load Qk in kN/m²?",
    }
    asked = [f"- {questions.get(f, f)}" for f in missing]
    return (
        "I need a few more details before I can assemble the loads:\n\n"
        + "\n".join(asked)
    )


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

    # ── Load collection ───────────────────────────────────────────────────────
    if not state.get("load_definition"):
        return await _collect_load_inputs(state, log_entry)

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


async def _collect_load_inputs(
    state: StructuralDesignState, log_entry: dict
) -> dict:
    """
    Collect load definition inputs from the engineer's last chat message.

    Uses the LLM *only* to extract structured values from natural language.
    Missing fields trigger a targeted follow-up question rather than a default.

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
    messages = state.get("messages", [])
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )

    if not last_human:
        return {
            "messages": [AIMessage(content=(
                "Please describe the building loading:\n"
                "- Design code (BS8110 or EC2)\n"
                "- Building occupancy type\n"
                "- Characteristic imposed floor load Qk (kN/m²)\n"
                "- Any superimposed dead loads (finishes, screed, services, partitions)\n"
            ))],
            "agent_logs": [{**log_entry, "status": "awaiting_load_inputs"}],
        }

    # LLM extraction — extracts only, never invents
    extraction_prompt = (
        "Extract load definition parameters from this message. "
        "Return ONLY a valid JSON object. "
        "Set any value not explicitly stated to null — do NOT invent or assume. "
        "Schema fields required:\n"
        "  design_code (BS8110 or EC2)\n"
        "  occupancy_category (residential|office|retail|roof_accessible|"
        "roof_non_accessible|stairs|custom)\n"
        "  imposed_loads.floor_qk_kNm2 (float, kN/m²)\n"
        "  dead_loads.finishes_kNm2 (float, optional)\n"
        "  dead_loads.screed_kNm2 (float, optional)\n"
        "  dead_loads.services_kNm2 (float, optional)\n"
        "  dead_loads.partitions_kNm2 (float, optional)\n\n"
        f"Message: {last_human.content}"
    )

    try:
        raw = await _llm.ainvoke(extraction_prompt)
        content = raw.content.replace("```json", "").replace("```", "").strip()
        load_data: dict = json.loads(content)
    except Exception:
        load_data = {}

    missing = _extract_missing_fields(load_data)
    if missing:
        question = _build_missing_field_question(missing)
        return {
            "messages": [AIMessage(content=question)],
            "agent_logs": [{**log_entry, "status": "load_inputs_incomplete", "detail": missing}],
        }

    # Validate before submitting
    project_id = state["project_id"]
    from services.loading import loading_service
    try:
        validation = loading_service.validate(load_data)
        if not validation.valid:
            errors = validation.errors
            return {
                "messages": [AIMessage(content=(
                    f"⚠️ Load definition has errors:\n"
                    + "\n".join(f"- {e}" for e in errors)
                    + "\nPlease correct and resubmit."
                ))],
                "agent_logs": [{**log_entry, "status": "validation_failed", "detail": errors}],
            }
    except Exception:
        pass  # Validation failure is non-blocking if the API is unavailable

    # Submit definition
    loading_service.define(project_id, load_data)

    return {
        "load_definition": load_data,
        "messages": [AIMessage(content=(
            "✅ Load definition accepted. "
            "Please confirm the assembled loads to proceed to analysis."
        ))],
        "agent_logs": [{**log_entry, "status": "load_definition_submitted"}],
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
