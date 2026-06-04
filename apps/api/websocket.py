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


async def run_or_resume_graph(project_id: str, input_state: dict[str, Any] | None) -> None:
    """
    Run or resume the LangGraph agent pipeline for the project,
    broadcasting all events to all active WebSocket connections.

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
    
    state_to_run = input_state
    if state_to_run is not None:
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
