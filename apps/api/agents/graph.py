"""
services/agents/graph.py
========================
LangGraph definition and compilation.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.state import StructuralDesignState
from agents.parser import parser_node
from agents.analyst import analyst_node
from agents.designer import designer_node
from agents.drafter import drafter_node
from agents.supervisor import supervisor_node, supervisor_router
from agents.gates import (
    geometry_verification_gate, geometry_gate_router,
    loading_confirmation_gate, loading_gate_router,
    design_confirmation_gate, designer_router,
    drawing_review_gate, drawing_gate_router
)

workflow = StateGraph(StructuralDesignState)

# Nodes
workflow.add_node("supervisor_agent", supervisor_node)
workflow.add_node("vision_agent", parser_node)
workflow.add_node("geometry_gate", geometry_verification_gate)
workflow.add_node("analyst_agent", analyst_node)
workflow.add_node("loading_gate", loading_confirmation_gate)
workflow.add_node("designer_agent", designer_node)
workflow.add_node("design_gate", design_confirmation_gate)
workflow.add_node("drafting_agent", drafter_node)
workflow.add_node("drawing_gate", drawing_review_gate)

workflow.set_entry_point("supervisor_agent")

workflow.add_conditional_edges(
    "supervisor_agent",
    supervisor_router,
    {
        "vision":    "vision_agent",
        "analyst":   "analyst_agent",
        "designer":  "designer_agent",
        "drafting":  "drafting_agent",
        "end":        END
    }
)

workflow.add_edge("vision_agent", "geometry_gate")

workflow.add_conditional_edges(
    "geometry_gate",
    geometry_gate_router,
    {
        "confirmed": "analyst_agent",
        "waiting":    END
    }
)

workflow.add_edge("analyst_agent", "loading_gate")

workflow.add_conditional_edges(
    "loading_gate",
    loading_gate_router,
    {
        "confirmed": "designer_agent",
        "waiting":    END
    }
)

workflow.add_conditional_edges(
    "designer_agent",
    designer_router,
    {
        "waiting_confirmation": "design_gate",
        "reanalysis_needed":  "analyst_agent",
        "confirmed":          "design_gate",
        "waiting":             END
    }
)

workflow.add_conditional_edges(
    "design_gate",
    lambda state: "confirmed" if state.get("design_confirmed") else "waiting",
    {
        "confirmed": "drafting_agent",
        "waiting":    END
    }
)

workflow.add_edge("drafting_agent", "drawing_gate")

workflow.add_conditional_edges(
    "drawing_gate",
    drawing_gate_router,
    {
        "confirmed":     END,
        "design_change": "designer_agent",
        "waiting": END
    }
)

memory = MemorySaver()
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=[
        "geometry_gate",
        "loading_gate",
        "design_gate",
        "drawing_gate"
    ]
)
