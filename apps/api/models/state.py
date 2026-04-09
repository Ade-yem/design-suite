from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[List[Any], add_messages]
    image_data: str | None
    extracted_params: Dict[str, Any] | None
    selected_standard: str | None
    analysis_data: Dict[str, Any] | None
    design_results: List[Any] | None
    error: str | None
