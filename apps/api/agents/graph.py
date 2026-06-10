"""
services/agents/graph.py
========================
LangGraph definition and compilation.

The compiled graph is exposed as ``app`` (MemorySaver checkpointer, suitable
for development / single-instance deployments).  For production use
``build_app(checkpointer)`` with a ``PostgreSaver`` or ``RedisSaver`` so that
pipeline state survives server restarts and horizontal scaling.

  from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
  async with AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL) as cp:
      await cp.setup()
      app = build_app(cp)
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.state import StructuralDesignState
from agents.parser import parser_node
from agents.analyst import analyst_node, analyst_router
from agents.designer import designer_node
from agents.drafter import drafter_node
from agents.supervisor import supervisor_node, supervisor_router
from agents.gates import (
    geometry_verification_gate, geometry_gate_router,
    loading_confirmation_gate, loading_gate_router,
    design_confirmation_gate, designer_router,
    drawing_review_gate, drawing_gate_router
)

# pyrefly: ignore [bad-specialization]
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

# The analyst gathers the design brief / loads conversationally over several
# turns.  While it is still collecting it routes to END so the next engineer
# message re-enters the node fresh; once analysis is complete it advances to the
# loading-confirmation gate.
workflow.add_conditional_edges(
    "analyst_agent",
    analyst_router,
    {
        "awaiting_input": END,
        "analysis_done":  "loading_gate",
    }
)

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

_INTERRUPT_BEFORE = [
    "geometry_gate",
    "loading_gate",
    "design_gate",
    "drawing_gate",
]


def build_app(checkpointer: Any = None):
    """Compile the workflow with the given checkpointer.

    Pass a ``PostgreSaver`` or ``RedisSaver`` in production so pipeline state
    survives restarts.  Defaults to ``MemorySaver`` (dev / single-instance only).
    """
    if checkpointer is None:
        checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer, interrupt_before=_INTERRUPT_BEFORE)


# Default compiled app — MemorySaver is fine for development.
# Replace with build_app(PostgreSaver(...)) via the FastAPI lifespan for production.
app = build_app()
