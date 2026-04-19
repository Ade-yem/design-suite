"""
services/agents/drafter.py  (Drafting Agent)
============================================
Drafting Agent node — the "Hands" of the pipeline.

Responsibilities
----------------
1. Generate structural canvas drawings for all designed members.
2. Build the layer package for the IDE Canvas panel.
3. Handle direct manipulation feedback (Canvas edits → limit state checks).
4. Prompt Gate 4 for drawing review.

Rule: This agent produces drawing commands deterministically via the
      drawing_generators. It does not use the LLM to invent geometry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from agents.api_client import api_client, poll_job_until_complete
from core.drawing import generate_drawing_commands
from agents.state import StructuralDesignState

logger = logging.getLogger(__name__)


def _build_layer_package(drawing_commands: list[dict]) -> dict:
    """Build layer definitions for the IDE Canvas panel."""
    layers = []
    # Simplified layer generation based on drawing commands
    for m in drawing_commands:
        mid = m["member_id"]
        mtype = m["member_type"]
        layers.append({
            "id": f"layer_{mid}",
            "label": f"{mtype.capitalize()} {mid}",
            "member_type": mtype,
            "visible": True,
            "color": "#ffffff"
        })
    return {"layers": layers, "bounds": {"width": 2000, "height": 2000}}


async def drafter_node(state: StructuralDesignState) -> dict:
    """
    Drafting Agent LangGraph node.
    """
    project_id = state["project_id"]
    log_entry = {
        "agent": "drafting",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    design_results = state.get("design_results", {})
    members = design_results.get("members", [])
    
    drawing_commands = []
    
    for member in members:
        try:
            cmds = generate_drawing_commands(member)
            drawing_commands.append({
                "member_id": member["member_id"],
                "member_type": member["member_type"],
                "commands": cmds
            })
        except Exception as e:
            logger.warning(f"Failed to generate drawing for {member.get('member_id')}: {e}")

    layer_package = _build_layer_package(drawing_commands)

    # In a full implementation we would POST these to a drawings router.
    # For now we just put them in state.

    message = f"""
**Drawings Generated.**

Section details and elevations are now visible in the Canvas panel.
{len(drawing_commands)} member drawing(s) produced.

- Use the Layer Manager to toggle between member types
- Click any member on the canvas to inspect or edit reinforcement
- Bar marks are cross-referenced to the reinforcement schedule

Please review the drawings and click **Confirm Drawings** when satisfied,
or click any member directly to make adjustments.
"""

    return {
        "drawing_commands": drawing_commands,
        "layer_package": layer_package,
        "pipeline_status": "drawings_generated",
        "messages": [AIMessage(content=message.strip())],
        "agent_logs": [{**log_entry, "status": "complete"}]
    }

async def handle_canvas_edit(state: StructuralDesignState, member_id: str, edit_type: str, new_value: float) -> dict:
    """
    Handle a direct manipulation edit from the canvas.
    """
    project_id = state["project_id"]
    try:
        result = await api_client.put(
            f"/api/v1/design/{project_id}/member/{member_id}",
            json={"parameter": edit_type, "value": new_value, "reason": "canvas edit"}
        )
        
        if result.get("status") == "FAIL": # Assume failed override
             return {
                 "messages": [AIMessage(content=f"⚠️ Edit rejected. Changing {edit_type} to {new_value} causes a limit state failure.")],
                 "revert_drawing": member_id
             }

        # Success - regenerate the single drawing
        updated_member = result.get("result", {})
        if updated_member:
             new_cmds = generate_drawing_commands(updated_member)
             return {
                 "messages": [AIMessage(content=f"✅ {member_id} updated. {edit_type} changed to {new_value}. All checks pass.")],
                 "updated_drawing": {
                     "member_id": member_id,
                     "commands": new_cmds
                 }
             }
             
    except Exception as e:
        return {"messages": [AIMessage(content=f"❌ Edit failed: {e}")]}
    return {}
