"""
services/agents/supervisor.py
=============================
Supervisor Agent node — the intelligent orchestrator of the pipeline.

The Supervisor is the **entry point** for every user message.  It is
responsible for one job: deciding which downstream agent node should
handle the current turn.

Decision logic (in priority order)
-----------------------------------
1. **LLM routing** — an LLM analyses the full pipeline context (status
   flags, recent message history, error state) and returns a structured
   JSON block nominating the ``next_node``.
2. **Deterministic fallback** — if the LLM output is malformed, the route
   is invalid, or the LLM call itself fails, the router falls back to the
   hardcoded ``pipeline_status → node`` mapping used in the original
   implementation.  This guarantees the graph can never lock up.

Safety contract
---------------
- The Supervisor **never** decides to pass or fail a gate.  Gates
  (``geometry_gate``, ``loading_gate``, ``design_gate``, ``drawing_gate``)
  remain hard ``interrupt_before`` barriers controlled exclusively by
  human confirmation via the frontend.
- The LLM call is tagged ``"utility"`` so its streaming tokens are
  **never** broadcast to the engineer's chat panel.
- Routing to a node that has unmet prerequisites (e.g. routing to
  ``designer`` before ``geometry_verified``) is blocked by the
  prerequisite check in ``_validate_and_clamp``.

Notes
------------------------------------------
- ``supervisor_node`` always returns a *partial* state dict (LangGraph
  will merge it with the current state).
- ``supervisor_router`` reads ``state["next_node"]`` and returns a string
  matching one of the graph edges defined in ``graph.py``.
- ``supervisor_node`` may return an ``AIMessage`` only when the LLM
  determined a non-obvious routing change and elected to send a
  transparency message to the engineer (e.g. "Returning to loading
  stage because …").  Routine routing (following the normal sequence) is
  silent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from agents import _get_llm
from agents.state import StructuralDesignState
from agents.designer import handle_design_override

logger = logging.getLogger(__name__)

# ─── Valid node targets ────────────────────────────────────────────────────────

_VALID_NODES = frozenset({"geometry", "analyst", "designer", "drafting", "end"})

# ─── Deterministic fallback mapping ───────────────────────────────────────────

_STATUS_TO_NODE: dict[str, str] = {
    "created":            "geometry",
    "file_uploaded":      "geometry",
    "geometry_verified":  "analyst",
    "loading_defined":    "analyst",
    "analysis_complete":  "designer",
    "design_complete":    "designer",
    "drawings_generated": "drafting",
    "report_generated":   "end",
}

# ─── Prerequisite guards ──────────────────────────────────────────────────────

_NODE_PREREQS: dict[str, list[str]] = {
    "analyst":  ["geometry_verified"],
    "designer": ["geometry_verified", "loading_confirmed", "analysis_complete"],
    "drafting": ["geometry_verified", "loading_confirmed", "analysis_complete", "design_complete"],
}


def _validate_and_clamp(
    proposed: str,
    state: StructuralDesignState,
) -> str:
    """
    Ensure the LLM's proposed route satisfies pipeline prerequisites.

    If the proposed node requires state flags that are not yet set, fall
    back to the deterministic mapping derived from ``pipeline_status``.

    Parameters
    ----------
    proposed : str
        Node name proposed by the LLM.
    state : StructuralDesignState
        Current pipeline state.

    Returns
    -------
    str
        A validated node name, possibly corrected to a safe fallback.
    """
    if proposed not in _VALID_NODES:
        logger.warning(
            "Supervisor: LLM proposed unknown node '%s' — using fallback.", proposed
        )
        return _fallback_node(state)

    prereqs = _NODE_PREREQS.get(proposed, [])
    for flag in prereqs:
        if not state.get(flag):
            logger.warning(
                "Supervisor: LLM proposed '%s' but prerequisite '%s' is not met — "
                "using fallback.",
                proposed,
                flag,
            )
            return _fallback_node(state)

    return proposed


def _fallback_node(state: StructuralDesignState) -> str:
    """
    Return the deterministic next node based on the current pipeline status.

    Parameters
    ----------
    state : StructuralDesignState

    Returns
    -------
    str
        A node name from ``_VALID_NODES``.
    """
    status = state.get("pipeline_status", "created")
    return _STATUS_TO_NODE.get(status, "end")


# ─── LLM prompt construction ──────────────────────────────────────────────────

def _build_supervisor_prompt(state: StructuralDesignState) -> str:
    """
    Construct the structured context prompt sent to the LLM Supervisor.

    Includes the pipeline status flags, error state, and the last three
    engineer messages so the model can understand conversational intent.

    Parameters
    ----------
    state : StructuralDesignState

    Returns
    -------
    str
        A fully-formed prompt string.
    """
    # Collect last 3 human messages
    recent_human: list[str] = []
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            text = getattr(msg, "content", "") or getattr(msg, "text", "")
            if text:
                recent_human.append(text)
            if len(recent_human) >= 3:
                break
    recent_human = list(reversed(recent_human))

    flags = {
        "pipeline_status":      state.get("pipeline_status", "created"),
        "geometry_verified":    state.get("geometry_verified", False),
        "loading_confirmed":    state.get("loading_confirmed", False),
        "analysis_complete":    state.get("analysis_complete", False),
        "design_complete":      state.get("design_complete", False),
        "drawing_confirmed":    state.get("drawing_confirmed", False),
        "reanalysis_triggered": state.get("reanalysis_triggered", False),
        "current_error":        state.get("current_error"),
        "failed_analysis":      state.get("failed_members_analysis", []),
        "failed_design":        state.get("failed_members_design", []),
    }

    return (
        "You are the Supervisor of a structural engineering AI pipeline that guides a "
        "structural engineer through the design of a building frame from DXF upload to "
        "reinforced concrete detailing.\n\n"
        "Your ONLY job is to decide which pipeline node should handle the next turn.\n\n"
        "Pipeline nodes available:\n"
        "  - \"geometry\"  : Review uploaded DXF/PDF geometry. Use when file is not yet uploaded or geometry is not yet verified.\n"
        "  - \"analyst\"   : Collect design brief (materials, loads, occupancy) and run structural analysis. Use after geometry is verified, or when the engineer wants to change loading/materials.\n"
        "  - \"designer\"  : Run reinforced concrete design to BS 8110/EC2. Use after analysis is complete, or when the engineer wants to modify member dimensions.\n"
        "  - \"drafting\"  : Generate 2D structural drawings. Use after design is complete and confirmed.\n"
        "  - \"end\"       : No further action needed (pipeline complete, or waiting for human gate confirmation).\n\n"
        "SAFETY RULES (never violate these):\n"
        "  - You may NEVER route to a node whose prerequisites are not met (e.g. do not route to 'designer' if analysis is not complete).\n"
        "  - You do NOT control gate confirmations — those are always human actions.\n"
        "  - If the engineer's message does not require a pipeline stage change, route to the logically next stage.\n\n"
        f"Current pipeline flags:\n{json.dumps(flags, indent=2)}\n\n"
        f"Recent engineer messages (oldest first):\n"
        + ("\n".join(f"  [{i+1}] \"{m}\"" for i, m in enumerate(recent_human)) if recent_human else "  (none)\n")
        + "\n\n"
        "Respond with ONLY a valid JSON object — no markdown, no explanation outside the JSON:\n"
        "{\n"
        "  \"next_node\": \"<node_name>\",\n"
        "  \"reason\": \"<one sentence explaining why>\",\n"
        "  \"send_message\": <true|false>,\n"
        "  \"message\": \"<optional short message to show the engineer if send_message is true>\"\n"
        "}"
    )


# ─── Node ─────────────────────────────────────────────────────────────────────


async def supervisor_node(state: StructuralDesignState) -> dict[str, Any]:
    """
    LLM-driven Supervisor Agent LangGraph node.

    Analyses the current pipeline state and recent engineer messages via an
    LLM call to determine the best next node to activate.  Falls back to a
    deterministic status-based mapping if the LLM output cannot be parsed or
    proposes an invalid route.

    Parameters
    ----------
    state : StructuralDesignState
        Full shared pipeline state.

    Returns
    -------
    dict
        Partial state update containing at minimum:
        - ``next_node``        : validated routing target
        - ``supervisor_reason``: one-line explanation for logs
        - ``agent_logs``       : structured log entry
        - ``messages``         : list containing at most one ``AIMessage``
                                 (only emitted when the LLM sets ``send_message=True``)
    """
    log_entry: dict[str, Any] = {
        "agent": "supervisor",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ── Handle engineer design overrides mid-pipeline ─────────────────────────
    # Quick shortcut before hitting the LLM: if the most recent human message
    # looks like a dimension override and we are in a design stage, delegate
    # immediately to the designer override handler.
    messages_list = state.get("messages", [])
    last_human = next(
        (m for m in reversed(messages_list) if isinstance(m, HumanMessage)), None
    )
    if (
        last_human
        and state.get("pipeline_status") in ("design_complete", "analysis_complete")
        and _is_design_override(last_human)
    ):
        logger.debug("Supervisor: fast-path design override detected.")
        override_result = await handle_design_override(state, _get_message_text(last_human))
        # Ensure routing still advances correctly after the override
        override_result.setdefault("next_node", "designer")
        override_result.setdefault("supervisor_reason", "Design override detected in engineer message.")
        override_result.setdefault("agent_logs", [])
        override_result["agent_logs"].append(
            {**log_entry, "status": "design_override", "detail": "fast-path"}
        )
        return override_result

    # ── LLM routing ──────────────────────────────────────────────────────────
    proposed_node: str = _fallback_node(state)
    reason: str = "deterministic fallback (LLM not invoked)"
    messages_out: list = []

    try:
        prompt = _build_supervisor_prompt(state)
        raw = await _get_llm().ainvoke(
            prompt,
            config={"tags": ["utility"]},  # Never streams to chat panel
        )
        content = getattr(raw, "text", "") or getattr(raw, "content", "")
        content = content.strip()

        # Strip markdown fences if the model wrapped the JSON
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        parsed: dict = json.loads(content)
        llm_node: str = parsed.get("next_node", "")
        llm_reason: str = parsed.get("reason", "")
        send_message: bool = bool(parsed.get("send_message", False))
        user_message: str = parsed.get("message", "")

        # Validate and clamp to a safe node
        validated = _validate_and_clamp(llm_node, state)
        proposed_node = validated
        reason = llm_reason

        logger.info(
            "Supervisor: LLM proposed '%s' (validated: '%s') — %s",
            llm_node,
            validated,
            llm_reason,
        )

        # Only emit a chat message if the LLM explicitly requested it
        if send_message and user_message:
            messages_out.append(AIMessage(content=user_message))

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Supervisor: LLM routing failed (%s) — using deterministic fallback '%s'.",
            exc,
            proposed_node,
        )

    return {
        "next_node": proposed_node,
        "supervisor_reason": reason,
        "messages": messages_out,
        "agent_logs": [{**log_entry, "status": "routing", "detail": f"→ {proposed_node}: {reason}"}],
    }


# ─── Router ────────────────────────────────────────────────────────────────────


def supervisor_router(state: StructuralDesignState) -> str:
    """
    Read the ``next_node`` value written by ``supervisor_node`` and return
    it to LangGraph as the edge target.

    Falls back to the deterministic mapping if ``next_node`` is absent or
    invalid (e.g. on a graph resume from a checkpoint that pre-dates this
    field).

    Parameters
    ----------
    state : StructuralDesignState

    Returns
    -------
    str
        One of: ``"geometry"`` | ``"analyst"`` | ``"designer"`` |
        ``"drafting"`` | ``"end"``.
    """
    node = state.get("next_node", "")
    if node in _VALID_NODES:
        return node
    # Legacy / missing state: fall back to deterministic map
    fallback = _fallback_node(state)
    logger.debug(
        "supervisor_router: next_node='%s' not valid — falling back to '%s'.",
        node,
        fallback,
    )
    return fallback


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _get_message_text(msg: HumanMessage) -> str:
    """
    Safely extract the text content from a ``HumanMessage``.

    LangChain messages expose text via ``.content`` (string) or ``.text``
    (older API).  This helper normalises both.

    Parameters
    ----------
    msg : HumanMessage

    Returns
    -------
    str
    """
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    text = getattr(msg, "text", None)
    if isinstance(text, str):
        return text
    return ""


def _is_design_override(msg: HumanMessage) -> bool:
    """
    Heuristic check: does the engineer's message look like a member dimension
    override request?

    This fast-path avoids an unnecessary LLM round-trip for the most common
    mid-design interaction.  The LLM override handler itself does the precise
    extraction.

    Parameters
    ----------
    msg : HumanMessage

    Returns
    -------
    bool
    """
    text = _get_message_text(msg).lower()
    has_change_verb = any(kw in text for kw in ("change", "update", "set", "adjust", "modify"))
    has_dimension_kw = any(kw in text for kw in ("width", "depth", "cover", "b_mm", "h_mm", "to"))
    return has_change_verb and has_dimension_kw
