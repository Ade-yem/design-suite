"""
services/agents/supervisor.py
=============================
Supervisor Agent node — the orchestrator and router.
"""
from langchain_core.messages import AIMessage, HumanMessage
from agents.state import StructuralDesignState
from agents.designer import handle_design_override
import json

def is_design_override(message: HumanMessage) -> bool:
    # A simplistic heuristic; could be improved with LLM router
    text = message.content.lower()
    return "change" in text and ("width" in text or "depth" in text or "cover" in text or "to" in text)

async def supervisor_node(state: StructuralDesignState) -> dict:
    messages = state.get("messages", [])
    if not messages:
        return {}
        
    last_message = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_message and is_design_override(last_message) and state.get("pipeline_status") in ("design_complete", "analysis_complete"):
        return await handle_design_override(state, last_message.content)
        
    return {}

def supervisor_router(state: StructuralDesignState) -> str:
    pipeline_status = state.get("pipeline_status", "created")
    routing_map = {
        "created":            "vision",
        "file_uploaded":      "vision",
        "geometry_verified":  "analyst",
        "loading_defined":    "analyst",
        "analysis_complete":  "designer",
        "design_complete":    "designer",
        "drawings_generated": "drafting",
        "report_generated":   "end"
    }
    return routing_map.get(pipeline_status, "end")
