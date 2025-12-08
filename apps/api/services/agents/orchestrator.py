from langgraph.graph import StateGraph, END
from services.agents.state import AgentState
from services.agents.parser import parser_node
from services.agents.designer import designer_node

# Define the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("parser", parser_node)
workflow.add_node("designer", designer_node)

# Define edges
# Parser -> End (Wait for user input) -> Designer
workflow.set_entry_point("parser")
workflow.add_edge("parser", END) 
# Note: In a real LangGraph with human-in-the-loop, we'd have a conditional edge or interrupt.
# For this stateless API approach, we'll manually invoke specific nodes based on input.
# But to define the graph structure:
workflow.add_edge("designer", END)

# Compile the graph
app = workflow.compile()
