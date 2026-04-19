from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.parser import parser_node
from agents.analyst import analyst_node
from agents.designer import designer_node
from agents.drafter import drafter_node

# Define the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("parser", parser_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("designer", designer_node)
workflow.add_node("drafter", drafter_node)

# Define edges
workflow.set_entry_point("parser")
workflow.add_edge("parser", END)  # Human-in-the-loop after parsing

# When resumed for analysis/design:
workflow.add_edge("analyst", "designer")
workflow.add_edge("designer", "drafter")
workflow.add_edge("drafter", END)

# Compile the graph
app = workflow.compile()
