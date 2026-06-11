"""
websocket.py
============
WebSocket router for connecting the IDE frontend to the LangGraph orchestration layer.

Streams agent messages, status logs, human-gates, and drawing commands
in real-time to the React UI.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from langchain_core.messages import HumanMessage

import agents.graph as _agent_graph
from auth.auth_db import SQLAlchemyUserDatabase
from auth.backend import auth_backend
from auth.manager import UserManager
from db.models.oauth import OAuthAccount
from db.models.user import User
from db.session import get_session_maker
from storage.project_store import project_store

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages active WebSocket connections mapped by project ID.
    Enables direct real-time broadcasting from async background tasks.
    """
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        """Register a new active WebSocket connection for a project."""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        self.active_connections[project_id].add(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        """Unregister a closed WebSocket connection."""
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast(self, project_id: str, message: dict) -> None:
        """Broadcast a JSON message to all active WebSockets for a project."""
        if project_id in self.active_connections:
            sockets = list(self.active_connections[project_id])
            for websocket in sockets:
                try:
                    await websocket.send_json(message)
                except Exception:
                    self.disconnect(project_id, websocket)


manager = ConnectionManager()


# Graph nodes that speak to the engineer.  Their appended ``messages`` are the
# canonical chat channel — broadcast on node completion (``on_chain_end``).
_AGENT_NODE_NAMES: frozenset[str] = frozenset({
    "supervisor_agent", "vision_agent", "analyst_agent",
    "designer_agent", "drafting_agent",
    "geometry_gate", "loading_gate", "design_gate", "drawing_gate",
})

# Agent-log statuses that mean the node is now waiting on an engineer decision.
# Any message carried alongside one of these must surface the chat panel.
_DECISION_STATUSES: frozenset[str] = frozenset({
    "awaiting_unit_confirmation", "awaiting_verification",
    "awaiting_design_considerations", "design_considerations_incomplete",
    "design_considerations_complete",  # parameters summary → confirm loads
    "awaiting_custom_qk", "validation_failed", "failures_detected",
})


def _node_requires_input(output: Any) -> bool:
    """
    Decide whether a node's output represents a point where the engineer must act.

    Reads the ``agent_logs`` the node appended this turn and matches their
    ``status`` against the known decision statuses (plus a couple of permissive
    patterns) so new "awaiting_*"/"*_incomplete" statuses are covered too.
    """
    if not isinstance(output, dict):
        return False
    for entry in output.get("agent_logs", []) or []:
        status_val = str((entry or {}).get("status", ""))
        if (
            status_val in _DECISION_STATUSES
            or status_val.startswith("awaiting")
            or status_val.endswith("incomplete")
        ):
            return True
    return False


def _extract_agent_texts(output: Any) -> list[str]:
    """Return the human-facing text of any AI messages a node appended this turn."""
    if not isinstance(output, dict):
        return []
    texts: list[str] = []
    for msg in output.get("messages", []) or []:
        # LangChain message objects expose ``.type == "ai"`` and ``.content``.
        if getattr(msg, "type", None) == "ai":
            content = getattr(msg, "content", "")
        elif isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content", "")
        else:
            continue
        if isinstance(content, str) and content.strip():
            texts.append(content)
    return texts


def serialize_message(msg: Any) -> dict[str, str] | None:
    """
    Serialize a LangChain message object or message dictionary to a standardized frontend format.

    Parameters
    ----------
    msg : Any
        The message object or dictionary to serialize.

    Returns
    -------
    dict[str, str] | None
        A dictionary with 'role' and 'content' keys, or None if the message is a system message or invalid.
    """
    if hasattr(msg, "content"):
        content = msg.content
    elif isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        return None

    if not isinstance(content, str) or not content.strip():
        return None

    msg_type = getattr(msg, "type", None)
    if msg_type == "system":
        return None
    elif msg_type == "human":
        role = "user"
    elif msg_type == "ai":
        role = "assistant"
    elif isinstance(msg, dict):
        if msg.get("type") == "system" or msg.get("role") == "system":
            return None
        r = msg.get("role")
        if r in ("user", "human"):
            role = "user"
        elif r in ("assistant", "ai"):
            role = "assistant"
        else:
            role = "assistant"
    else:
        role = "assistant"

    return {
        "role": role,
        "content": content
    }


async def run_or_resume_graph(project_id: str, input_state: dict[str, Any] | None) -> None:
    """
    Run or resume the LangGraph agent pipeline for the project,
    broadcasting all events to all active WebSocket connections.

    Ensures that ``project_id`` and ``pipeline_status`` are always present in the
    running state dictionary, preventing KeyErrors when initiating or resuming
    the graph.

    Parameters
    ----------
    project_id : str
        Project identifier.
    input_state : dict[str, Any] | None
        Input state dictionary to run the graph with, or None to resume from checkpoint.
    """
    config = {"configurable": {"thread_id": project_id}}
    stored_status = await project_store.get_status(project_id)
    pipeline_status = stored_status.label() if stored_status is not None else "created"
    
    if input_state is None:
        state = await _agent_graph.app.aget_state(config)
        if state and state.next:
            state_to_run = None
        else:
            state_to_run = {
                "project_id": project_id,
                "pipeline_status": pipeline_status,
            }
    else:
        state_to_run = input_state
        state_to_run.update({
            "project_id": project_id,
            "pipeline_status": pipeline_status,
        })

    try:
        async for event in _agent_graph.app.astream_events(
            state_to_run,
            config=config,
            version="v2"
        ):
            # Stream agent messages to chat panel
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    await manager.broadcast(project_id, {
                        "type": "agent_message",
                        "content": chunk.content
                    })

            # Broadcast the messages a node appended to state when it finishes.
            # These static AIMessages (questions, summaries, narratives) are the
            # real chat channel — and ``requires_input`` tells the UI to surface
            # the chat panel whenever the engineer must make a decision.
            if (
                event["event"] == "on_chain_end"
                and event.get("name") in _AGENT_NODE_NAMES
            ):
                output = event.get("data", {}).get("output")
                requires_input = _node_requires_input(output)
                for text in _extract_agent_texts(output):
                    await manager.broadcast(project_id, {
                        "type": "agent_message",
                        "content": text,
                        "requires_input": requires_input,
                        "final": True,
                    })

            # Stream status log updates
            if event["event"] == "on_tool_end":
                await manager.broadcast(project_id, {
                    "type": "status_log",
                    "tool": event["name"],
                    "status": "complete"
                })

            # Signal human gate reached
            if event["name"] in [
                "geometry_gate", "loading_gate",
                "design_gate", "drawing_gate"
            ]:
                await manager.broadcast(project_id, {
                    "type": "gate_reached",
                    "gate": event["name"],
                    "action_required": "confirm"
                })

            # Stream drawing commands
            if event["event"] == "on_tool_end" and event["name"] == "generate_drawings":
                await manager.broadcast(project_id, {
                    "type": "drawing_commands",
                    "data": event["data"].get("output", {})
                })

            # Stream single drawing update
            if event["event"] == "on_tool_end" and event["name"] == "update_drawing":
                await manager.broadcast(project_id, {
                    "type": "drawing_update",
                    "data": event["data"].get("output", {})
                })
    except Exception as e:
        logger.error("Error executing agent graph: %s", str(e), exc_info=True)
        await manager.broadcast(project_id, {"type": "error", "message": str(e)})


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time bidirectional IDE client communication.

    Performs handshake token verification, isolates tenancy, and registers client
    to active connections pool.
    """
    # Extract token and verify
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("Rejecting WS connection for project %s: No token query param", project_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session_maker = get_session_maker()
    user = None
    try:
        async with session_maker() as session:
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)
            strategy = auth_backend.get_strategy()
            user = await strategy.read_token(token, user_manager)
    except Exception as e:
        logger.error("Error reading token during WS handshake: %s", str(e), exc_info=True)

    if not user or not user.is_active:
        logger.warning("Rejecting WS connection for project %s: Invalid token or inactive user", project_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Tenancy check
    project = await project_store.get(
        project_id,
        organisation_id=user.organisation_id,
        bypass_tenant_check=user.is_superuser
    )
    if not project:
        logger.warning("Rejecting WS connection for project %s: Tenant mismatch or project not found", project_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(project_id, websocket)
    logger.info("WebSocket connected for project %s", project_id)

    # Fetch and send existing chat history and active gate status upon connection
    try:
        config = {"configurable": {"thread_id": project_id}}
        state = await _agent_graph.app.aget_state(config)
        if state and state.values:
            messages = state.values.get("messages", [])
            serialized_messages = []
            for m in messages:
                serialized = serialize_message(m)
                if serialized:
                    serialized_messages.append(serialized)
            if serialized_messages:
                await websocket.send_json({
                    "type": "chat_history",
                    "messages": serialized_messages
                })
        
        if state and state.next:
            for node in state.next:
                if node in ("geometry_gate", "loading_gate", "design_gate", "drawing_gate"):
                    await websocket.send_json({
                        "type": "gate_reached",
                        "gate": node,
                        "action_required": "confirm"
                    })
    except Exception as e:
        logger.error("Error retrieving existing chat history / gate status: %s", str(e), exc_info=True)

    try:
        while True:
            # Wait for user input
            data = await websocket.receive_text()
            message = json.loads(data)
            
            user_text = message.get("content", "")
            if not user_text:
                continue

            # Run graph with human input message
            await run_or_resume_graph(project_id, {"messages": [HumanMessage(content=user_text)]})

    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
        logger.info("WebSocket disconnected for project %s", project_id)
    except Exception as e:
        manager.disconnect(project_id, websocket)
        logger.error("WebSocket error: %s", str(e), exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
