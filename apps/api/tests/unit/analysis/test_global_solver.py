import pytest
import numpy as np
from core.analysis.global_solver import GlobalMatrixSolver

def test_single_span_beam_reactions(empty_solver):
    """
    Test a 4m simply supported beam with a 10kN/m UDL.
    Expected Reactions: Fy = 20kN at each end.
    """
    E = 200e9
    A = 0.01
    I = 0.0001
    L = 4.0
    w = -10000.0 # 10kN/m downwards
    
    empty_solver.add_node("n0", 0.0, 0.0, [True, True, True])
    empty_solver.add_node("n1", L, 0.0, [False, True, False]) # Roller support
    
    empty_solver.add_element("b1", "n0", "n1", E, A, I)
    empty_solver.add_member_udl("b1", w)
    
    results = empty_solver.solve()
    reactions = results["reactions"]
    
    # Check vertical reactions (Propped Cantilever: R_fixed = 5wL/8, R_roller = 3wL/8)
    assert reactions["n0"]["Fy"] == pytest.approx(25000.0, abs=1e-3)
    assert reactions["n1"]["Fy"] == pytest.approx(15000.0, abs=1e-3)
    
    # Check moment at fixed end n0 (M_fixed = wL^2/8)
    assert abs(reactions["n0"]["M"]) == pytest.approx(20000.0, abs=1e-3)

def test_unstable_structure(empty_solver):
    """Expect ValueError for unstable structure (no supports)."""
    E = 200e9
    A = 0.01
    I = 0.0001
    
    empty_solver.add_node("n0", 0.0, 0.0, [False, False, False])
    empty_solver.add_node("n1", 4.0, 0.0, [False, False, False])
    empty_solver.add_element("b1", "n0", "n1", E, A, I)
    
    with pytest.raises(ValueError, match="Matrix is singular"):
        empty_solver.solve()

def test_nodal_load_portal_sway(portal_frame_setup):
    """Test a portal frame with a lateral point load."""
    portal_frame_setup.apply_nodal_load("n1", Fx=10000.0) # 10kN sway load
    
    results = portal_frame_setup.solve()
    reactions = results["reactions"]
    
    # Total horizontal reaction must equal applied load
    total_fx = reactions["n0"]["Fx"] + reactions["n3"]["Fx"]
    assert pytest.approx(total_fx, abs=1e-3) == -10000.0 # Negative because it opposes load
