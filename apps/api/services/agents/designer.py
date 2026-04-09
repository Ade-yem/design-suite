from services.agents.state import AgentState
from services.design.bs8110.beam import calculate_beam_reinforcement
from services.design.eurocode2.beam import calculate_beam_reinforcement_ec2
from langchain_core.messages import AIMessage
import json

def designer_node(state: AgentState):
    """
    Designer Agent:
    1. Reads extracted parameters and selected standard.
    2. Performs design.
    3. Returns design results.
    """
    extracted_params = state.get("extracted_params", {})
    selected_standard = state.get("selected_standard", "bs8110")
    analysis_data = state.get("analysis_data", {})
    
    if not extracted_params or not selected_standard:
        return {"error": "Missing parameters or standard for design."}

    members = extracted_params.get("members", {}).get("beams", []) # Filtering for beams
    results = []
    
    for member in members:
        member_id = member.get("id")
        # Get M and V from analysis_data if available
        beam_analysis = analysis_data.get("beam_analysis", {}).get(member_id, {})
        
        if beam_analysis and beam_analysis.get("results"):
            # Use critical values from analysis
            analysis_res = beam_analysis["results"][0]
            M = max(abs(analysis_res["M_left"]), abs(analysis_res["M_right"]), abs(analysis_res["M_span"]))
            # Shear force calculation (simplified from analysis or base UDL)
            total_load = beam_analysis.get("total_load_udl", 0)
            span_val = member.get("dimensions", {}).get("span", 5000)
            V = (total_load * span_val) / 2.0 # Standard shear
        else:
            # Fallback to defaults if analysis missing
            M = 150 * 10**6 # 150 kNm
            V = 100 * 10**3 # 100 kN

        b = member.get("dimensions", {}).get("width", 300)
        h = member.get("dimensions", {}).get("depth", 500)
        d = h - 50 # Effective depth approximation
        span = member.get("dimensions", {}).get("span", 5000)
        
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
                "As_prov": calc_res.get("As_prov"),
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
