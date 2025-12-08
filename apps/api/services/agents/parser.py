import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from services.agents.state import AgentState
import json

# Initialize Gemini Model
llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)

SYSTEM_PROMPT = """You are an expert structural engineer. 
Your task is to analyze the provided General Arrangement (GA) image and extract structural parameters.
Identify:
1. Structural Members (Beams, Columns, Slabs, Walls)
2. Dimensions (Span, Height, Thickness)
3. Connectivity (Which members support which)

Return the output as a valid JSON object with the following structure:
{
    "members": [
        {
            "id": "B1",
            "type": "Beam",
            "dimensions": {"span": 5000, "depth": 500, "width": 300},
            "supports": ["C1", "C2"]
        }
    ],
    "summary": "Brief description of the structure"
}
"""

def parser_node(state: AgentState):
    messages = state["messages"]
    image_data = state.get("image_data")
    
    if not image_data:
        return {"error": "No image data provided for parsing."}

    # Construct message with image
    # Note: image_data is expected to be a base64 string or url
    human_message = HumanMessage(
        content=[
            {"type": "text", "text": "Analyze this structural drawing."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
        ]
    )

    try:
        response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), human_message])
        
        # Parse JSON from response (simple cleanup)
        content = response.content.replace("```json", "").replace("```", "").strip()
        params = json.loads(content)
        
        return {"extracted_params": params, "messages": [response]}
    except Exception as e:
        return {"error": f"Parsing failed: {str(e)}"}
