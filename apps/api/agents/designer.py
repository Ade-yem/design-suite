"""
services/agents/designer.py  (Designer Agent)
==============================================
Designer Agent node — the "Local Material" of the pipeline.

Responsibilities
----------------
1. Run the design suite against completed analysis results.
2. Detect failed members and route them back to the Analyst for re-analysis
   if self-weight has changed by more than 5% (convergence loop).
3. Handle engineer design overrides (geometry changes, rebar selections)
   submitted mid-pipeline via the chat or canvas.
4. Summarise the completed design schedule before Gate 3.

Rule: This node never reads from ``services/design/`` directly.
      All computation flows via the FastAPI design router.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.api_client import api_client, poll_job_until_complete
from agents.state import StructuralDesignState

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)

# Self-weight change that triggers a re-analysis feedback
_SELF_WEIGHT_THRESHOLD_PCT = 5.0


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_failure_summary(failed_members: list[dict]) -> str:
    """
    Build a Markdown table of failed design members for the chat panel.

    Parameters
    ----------
    failed_members : list[dict]
        List of member result dicts where ``status == 'FAILED'``.

    Returns
    -------
    str
        Markdown-formatted failure summary.
    """
    rows = []
    for m in failed_members[:20]:
        mid = m.get("member_id", "?")
        reason = m.get("failure_reason") or m.get("notes") or "Limit state exceeded"
        rows.append(f"| {mid} | {reason} |")

    header = "| Member | Reason |\n|---|---|"
    return header + "\n" + "\n".join(rows)


def _build_design_summary(results: dict) -> str:
    """
    Build a human-readable Markdown summary of a completed design.

    Parameters
    ----------
    results : dict
        ``DesignResultsResponse`` dict from the design API.

    Returns
    -------
    str
        Markdown summary for the IDE chat panel.
    """
    members = results.get("members", [])
    total = len(members)
    failed = [m for m in members if m.get("status") == "FAILED"]
    warnings = [m for m in members if m.get("utilisation", 0) >= 0.9 and m.get("status") != "FAILED"]
    passed = total - len(failed) - len(warnings)

    lines = [
        f"**Design Complete — {total} member(s) to {results.get('design_code', 'BS8110')}**\n",
        f"- ✅ Passed:            {passed}",
        f"- ⚠️  Warnings (≥90%): {len(warnings)}",
        f"- ❌ Failed:            {len(failed)}",
    ]
    if warnings:
        warn_ids = ", ".join(m["member_id"] for m in warnings[:5])
        lines.append(f"\n**High utilisation (>90%):** {warn_ids}")

    lines.append(
        "\nThe complete reinforcement schedule is visible in the Canvas panel.\n"
        "Click **Confirm Design** when satisfied to proceed to drawing generation."
    )
    return "\n".join(lines)


# ─── Node ─────────────────────────────────────────────────────────────────────


async def designer_node(state: StructuralDesignState) -> dict:
    """
    Designer Agent LangGraph node.

    Entry conditions:
    - ``analysis_complete = True`` (standard path)
    - OR ``reanalysis_triggered = False`` after a convergence iteration
      (returning from the Analyst re-analysis loop)

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
        "agent": "designer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logs: list[dict] = []

    # ── Trigger full design run ───────────────────────────────────────────────
    try:
        design_resp = await api_client.post(
            f"/api/v1/design/run/{project_id}",
            json={"design_code": state.get("design_code", "BS8110")},
        )
        design_job_id: str = design_resp["job_id"]
        logs.append({**log_entry, "status": "design_started", "detail": design_job_id})
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Failed to start design run: {exc}")],
            "agent_logs": logs,
            "current_error": "DESIGN_FAILED",
        }

    # ── Poll with progress updates ────────────────────────────────────────────
    live_logs: list[dict] = []

    def _on_progress(status_dict: dict) -> None:
        live_logs.append({
            **log_entry,
            "status": "design_running",
            "detail": status_dict.get("current_step", ""),
            "pct": status_dict.get("progress_pct", 0),
        })

    try:
        await poll_job_until_complete(design_job_id, progress_cb=_on_progress)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Design run failed: {exc}")],
            "agent_logs": logs + live_logs,
            "current_error": "DESIGN_FAILED",
            "design_job_id": design_job_id,
        }

    # ── Fetch results ─────────────────────────────────────────────────────────
    try:
        results = await api_client.get(f"/api/v1/design/{project_id}/results")
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Could not retrieve design results: {exc}")],
            "agent_logs": logs + live_logs,
            "current_error": "DESIGN_FAILED",
        }

    members = results.get("members", [])

    # ── Check for hard failures ───────────────────────────────────────────────
    failed = [m for m in members if m.get("status") == "FAILED"]
    if failed:
        failure_summary = _build_failure_summary(failed)
        message = AIMessage(content=(
            f"⚠️ **Design Check — Action Required**\n\n"
            f"{len(failed)} member(s) failed limit state checks:\n\n"
            f"{failure_summary}\n\n"
            "**Options:**\n"
            "1. I can suggest revised dimensions automatically\n"
            "2. Specify new dimensions for each member\n"
            "3. Review loading assumptions\n\n"
            "What would you like to do?"
        ))
        return {
            "design_results": results,
            "design_job_id": design_job_id,
            "design_complete": False,
            "failed_members_design": [m["member_id"] for m in failed],
            "messages": [message],
            "agent_logs": logs + live_logs + [{**log_entry, "status": "failures_detected"}],
            "pipeline_status": "analysis_complete",
        }

    # ── Check for self-weight-driven re-analysis need ─────────────────────────
    members_needing_reanalysis: list[str] = []
    for m in members:
        if abs(m.get("self_weight_change_pct", 0)) > _SELF_WEIGHT_THRESHOLD_PCT:
            members_needing_reanalysis.append(m["member_id"])

    if members_needing_reanalysis:
        logger.info(
            "Self-weight change >%s%% detected for: %s — triggering re-analysis.",
            _SELF_WEIGHT_THRESHOLD_PCT,
            members_needing_reanalysis,
        )
        return {
            "design_results": results,
            "design_job_id": design_job_id,
            "design_complete": False,
            "failed_members_design": members_needing_reanalysis,
            "reanalysis_triggered": True,
            "messages": [AIMessage(content=(
                f"♻️ Self-weight changed by >{_SELF_WEIGHT_THRESHOLD_PCT}% "
                f"for {len(members_needing_reanalysis)} member(s) — "
                "re-running analysis for convergence…"
            ))],
            "agent_logs": logs + live_logs + [{
                **log_entry,
                "status": "reanalysis_triggered",
                "detail": members_needing_reanalysis,
            }],
        }

    # ── All passed ────────────────────────────────────────────────────────────
    summary = _build_design_summary(results)
    return {
        "design_results": results,
        "design_job_id": design_job_id,
        "design_complete": True,
        "failed_members_design": [],
        "reanalysis_triggered": False,
        "pipeline_status": "design_complete",
        "messages": [AIMessage(content=summary)],
        "agent_logs": logs + live_logs + [{**log_entry, "status": "complete"}],
        "current_error": None,
    }


# ─── Override handler (called by Supervisor) ──────────────────────────────────


async def handle_design_override(
    state: StructuralDesignState, user_message: str
) -> dict:
    """
    Apply an engineer geometry override to a designed member.

    Called by the Supervisor when it detects a design override intent in the
    engineer's message (e.g. "change beam B1 to 300×600").

    The LLM extracts the override parameters.  The result is validated against
    limit states via the FastAPI design router.  If self-weight changes
    significantly, the re-analysis loop is triggered automatically.

    Parameters
    ----------
    state : StructuralDesignState
        Current pipeline state.
    user_message : str
        Raw engineer message containing the override instruction.

    Returns
    -------
    dict
        Partial state update.
    """
    project_id = state["project_id"]
    log_entry = {
        "agent": "designer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # LLM extracts override — never invents values
    extraction_prompt = (
        "Extract a structural member design override from this message. "
        "Return ONLY a valid JSON object with these fields:\n"
        "  member_id (str)\n"
        "  b_mm (float | null)  — section width in mm\n"
        "  h_mm (float | null)  — section depth in mm\n"
        "  cover_mm (float | null)\n"
        "  fcu_MPa (float | null)  — BS8110 concrete strength\n"
        "  fck_MPa (float | null)  — EC2 concrete strength\n"
        "  fy_MPa (float | null)   — steel yield strength\n"
        "  reason (str)            — brief description of override reason\n\n"
        "Set any field not explicitly stated to null. Never invent values.\n\n"
        f"Message: \"{user_message}\""
    )

    try:
        raw = await _llm.ainvoke(extraction_prompt)
        content = raw.content.replace("```json", "").replace("```", "").strip()
        override_data: dict = json.loads(content)
    except Exception:
        return {
            "messages": [AIMessage(content=(
                "⚠️ I could not extract a clear override from that message. "
                "Please specify the member ID and the exact dimension or parameter to change "
                "(e.g. 'Change beam B1 width to 300 mm and depth to 600 mm')."
            ))],
            "agent_logs": [{**log_entry, "status": "override_parse_failed"}],
        }

    member_id = override_data.pop("member_id", None)
    if not member_id:
        return {
            "messages": [AIMessage(content=(
                "⚠️ Please specify which member to update (e.g. 'Change beam **B1** to 300×600')."
            ))],
        }

    try:
        result = await api_client.put(
            f"/api/v1/design/{project_id}/member/{member_id}",
            json=override_data,
        )
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Override failed for {member_id}: {exc}")],
            "agent_logs": [{**log_entry, "status": "override_api_failed"}],
        }

    warning = result.get("warning")
    reanalysis_url = result.get("reanalysis_url")

    if reanalysis_url:
        # Self-weight changed — trigger the convergence loop
        return {
            "reanalysis_triggered": True,
            "failed_members_design": [member_id],
            "messages": [AIMessage(content=(
                f"✅ Override applied to **{member_id}**.\n\n"
                f"⚠️ {warning}\n\n"
                "Re-running analysis for this member to converge self-weight…"
            ))],
            "agent_logs": [{**log_entry, "status": "override_reanalysis_triggered"}],
        }

    return {
        "messages": [AIMessage(content=(
            f"✅ **{member_id}** updated. All limit state checks pass."
        ))],
        "agent_logs": [{**log_entry, "status": "override_applied"}],
    }
