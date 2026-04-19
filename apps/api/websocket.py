"""
websocket.py
============
WebSocket router for connecting the IDE frontend to the LangGraph orchestration layer.

Streams agent messages, status logs, human-gates, and drawing commands
in real-time to the React UI.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from agents.graph import app as graph
from langchain_core.messages import HumanMessage
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for project {project_id}")

    try:
        while True:
            # Wait for user input
            data = await websocket.receive_text()
            message = json.loads(data)
            
            user_text = message.get("content", "")
            if not user_text:
                continue

            config = {"configurable": {"thread_id": project_id}}
            
            # Send streaming updates back to frontend
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=user_text)], "project_id": project_id, "pipeline_status": "created"},
                config=config,
                version="v2"
            ):
                # Stream agent messages to chat panel
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        await websocket.send_json({
                            "type": "agent_message",
                            "content": chunk.content
                        })

                # Stream status log updates
                if event["event"] == "on_tool_end":
                    await websocket.send_json({
                        "type": "status_log",
                        "tool": event["name"],
                        "status": "complete"
                    })

                # Signal human gate reached
                if event["name"] in [
                    "geometry_gate", "loading_gate",
                    "design_gate", "drawing_gate"
                ]:
                    await websocket.send_json({
                        "type": "gate_reached",
                        "gate": event["name"],
                        "action_required": "confirm"
                    })

                # Stream drawing commands
                if event["event"] == "on_tool_end" and event["name"] == "generate_drawings":
                    await websocket.send_json({
                        "type": "drawing_commands",
                        "data": event["data"].get("output", {})
                    })

                # Stream single drawing update
                if event["event"] == "on_tool_end" and event["name"] == "update_drawing":
                    await websocket.send_json({
                        "type": "drawing_update",
                        "data": event["data"].get("output", {})
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for project {project_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
             await websocket.send_json({"type": "error", "message": str(e)})
        except:
             pass
