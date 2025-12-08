from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from services.agents.orchestrator import app as agent_app
import base64
import json

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(
    message: str = Form(...),
    action: str = Form("parse"),
    data: str = Form(None),
    file: UploadFile = File(None)
):
    inputs = {"messages": []}
    
    if action == "parse":
        if not file:
            raise HTTPException(status_code=400, detail="Image file required for parsing")
        
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        contents = await file.read()
        image_b64 = base64.b64encode(contents).decode("utf-8")
        inputs["image_data"] = image_b64
        
        # Invoke Parser
        # We target the 'parser' node specifically or let the graph decide
        # For now, the graph entry point is parser
        result = agent_app.invoke(inputs)
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return result.get("extracted_params")

    elif action == "design":
        if not data:
            raise HTTPException(status_code=400, detail="Data required for design")
            
        try:
            payload = json.loads(data)
            inputs["extracted_params"] = payload.get("extracted_params")
            inputs["selected_standard"] = payload.get("selected_standard")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON data")
            
        # Invoke Designer
        # We need to manually trigger the designer node since our graph is simple
        # In a full LangGraph, we'd update state and let it flow
        from services.agents.designer import designer_node
        result = designer_node(inputs)
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
            
        # Return the last message content (summary) or raw results
        return json.loads(result["messages"][0].content)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
