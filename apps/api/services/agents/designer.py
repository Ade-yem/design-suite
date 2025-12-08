from services.agents.state import AgentState
from services.calculations.bs8110.beam import calculate_beam_reinforcement
from services.calculations.eurocode2.beam import calculate_beam_reinforcement_ec2
from langchain_core.messages import AIMessage
import json

def designer_node(state: AgentState):
    """
    Designer Agent:
    1. Reads extracted parameters and selected standard.
    2. Performs calculations.
    3. Returns design results.
    """
    extracted_params = state.get("extracted_params")
    selected_standard = state.get("selected_standard")
    
    if not extracted_params or not selected_standard:
        return {"error": "Missing parameters or standard for design."}
        
    members = extracted_params.get("members", [])
    results = []
    
    for member in members:
        # Default values for demo purposes if not extracted
        # In a real app, we'd ask the user or infer these
        M = 150 * 10**6 # 150 kNm
        V = 100 * 10**3 # 100 kN
        b = member.get("dimensions", {}).get("width", 300)
        h = member.get("dimensions", {}).get("depth", 500)
        d = h - 50 # Effective depth approximation
        span = member.get("span", 6000) # Default span
        
        if selected_standard == "bs8110":
            calc_res = calculate_beam_reinforcement(M, V, b, d, h, span)
        elif selected_standard == "eurocode2":
            calc_res = calculate_beam_reinforcement_ec2(M, V, b, d)
        else:
            calc_res = {"error": "Unknown standard"}
            
        results.append({
            "member_id": member.get("id"),
            "standard": selected_standard,
            "design_status": calc_res.get("status"),
            "reinforcement": {
                "As_req": calc_res.get("As_req"),
                "shear_links": calc_res.get("shear_links")
            },
            "notes": calc_res.get("notes")
        })
        
    # Create a summary message
    summary_msg = AIMessage(content=json.dumps({
        "type": "design_result",
        "results": results
    }))
    
    return {"design_results": results, "messages": [summary_msg]}
