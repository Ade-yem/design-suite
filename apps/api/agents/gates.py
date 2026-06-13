"""
services/agents/gates.py
========================
Human-in-the-loop gate definitions.
"""
from langchain_core.messages import AIMessage
from agents.state import StructuralDesignState
from services.files import file_service

async def geometry_verification_gate(state: StructuralDesignState) -> dict:
    if state.get("geometry_verified"):
        await file_service.verify_geometry(
            state['project_id'],
            corrections=state.get("geometry_corrections", []),
            notes="Gate 1 manual confirmation"
        )
        return {
            "agent_logs": [{"agent": "gate_1", "status": "passed"}],
            "messages": [AIMessage(content="✅ Geometry confirmed. Proceeding to load definition.")]
        }
    return {"agent_logs": [{"agent": "gate_1", "status": "waiting"}]}

def geometry_gate_router(state: StructuralDesignState) -> str:
    return "confirmed" if state.get("geometry_verified") else "waiting"


async def loading_confirmation_gate(state: StructuralDesignState) -> dict:
    if state.get("loading_confirmed"):
        return {
            "agent_logs": [{"agent": "gate_2", "status": "passed"}],
            "messages": [AIMessage(content="✅ Loads confirmed. Running structural analysis now.")]
        }
    return {"agent_logs": [{"agent": "gate_2", "status": "waiting"}]}

def loading_gate_router(state: StructuralDesignState) -> str:
    return "confirmed" if state.get("loading_confirmed") else "waiting"


async def design_confirmation_gate(state: StructuralDesignState) -> dict:
    if state.get("design_confirmed"):
        return {
            "agent_logs": [{"agent": "gate_3", "status": "passed"}],
            "messages": [AIMessage(content="✅ Design confirmed. Generating structural drawings now.")]
        }
    return {"agent_logs": [{"agent": "gate_3", "status": "waiting"}]}

def designer_router(state: StructuralDesignState) -> str:
    if state.get("reanalysis_triggered"):
        return "reanalysis_needed"
    if state.get("design_complete") and state.get("design_confirmed"):
        return "confirmed"
    if state.get("design_complete"):
        return "waiting_confirmation" # Route to gate
    return "waiting"


async def drawing_review_gate(state: StructuralDesignState) -> dict:
    if state.get("drawing_confirmed"):
        # Could trigger reports here
        return {
            "report_complete": True,
            "agent_logs": [{"agent": "gate_4", "status": "passed"}],
            "messages": [AIMessage(content="✅ Drawings confirmed. Pipeline complete.")]
        }
    return {"agent_logs": [{"agent": "gate_4", "status": "waiting"}]}

def drawing_gate_router(state: StructuralDesignState) -> str:
    if state.get("reanalysis_triggered"): return "design_change"
    if state.get("drawing_confirmed"): return "confirmed"
    return "waiting"
