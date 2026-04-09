from services.agents.state import AgentState
from services.load_analysis.solver import ContinuousBeamSolver, Span, UDL, PointLoad
from services.load_analysis.distribution import LoadDistribution
from typing import Dict, Any

def analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Analyst Agent Node:
    Takes parsed geometry and calculates load distribution and structural actions.
    """
    params = state.get("extracted_params")
    if not params:
        return {"error": "No extracted parameters found for analysis."}

    members = params.get("members", {})
    slabs = members.get("slabs", [])
    beams = members.get("beams", [])
    
    analysis_data = {
        "slab_distributions": {},
        "beam_analysis": {},
        "status": "Analysis completed"
    }

    # 1. Distribute loads from Slabs to Beams
    # We assume a default design load of 10.0 kN/m2 if not specified
    for slab in slabs:
        id_ = slab.get("id", "S1")
        dims = slab.get("dimensions", {})
        lx = dims.get("span", 3000)
        ly = dims.get("width", lx * 1.5)
        
        distribution = LoadDistribution.distribute_slab_load(lx, ly, design_load=10.0)
        analysis_data["slab_distributions"][id_] = distribution

    # 2. Analyze Beams
    # Grouping beams into continuous systems (Simplified: if IDs are like B1-1, B1-2, etc.)
    # For this implementation, we'll analyze them as individual spans but prepare the structure for continuity.
    for beam in beams:
        id_ = beam.get("id", "B1")
        dims = beam.get("dimensions", {})
        length = dims.get("span", 5000)
        
        # Determine loads on this beam
        # (Simplified coupling logic: find if a slab's long_beam_load should apply)
        applied_udl = 5.0 # Dead load of beam self-weight etc (kN/m)
        
        # Check if any slab is supported by this beam
        # In a real scenario, this uses the 'supports' key from the parser
        for slab_id, dist in analysis_data["slab_distributions"].items():
            # Mock logic: Slab supports even-numbered beams with long_beam_load
            # In production, this would match geometry.
            applied_udl += dist["long_beam_load"]
            break # Just take the first for example

        # Create Span and Solve
        span = Span(length=length, loads=[UDL(magnitude=applied_udl)])
        solver = ContinuousBeamSolver([span])
        results = solver.solve()
        
        analysis_data["beam_analysis"][id_] = {
            "results": results,
            "total_load_udl": applied_udl,
            "note": f"Analyzed single span for beam {id_}"
        }

    return {"analysis_data": analysis_data}
