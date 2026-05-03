import pytest
from core.analysis.global_solver import GlobalMatrixSolver
from core.analysis.beam_solver import SimplySupportedBeamSolver

@pytest.fixture
def empty_solver():
    """Returns a fresh, empty GlobalMatrixSolver instance."""
    return GlobalMatrixSolver()

@pytest.fixture
def simply_supported_beam():
    """
    Returns a SimplySupportedBeamSolver for a 5m beam.
    E = 200 GPa, I = 0.0001 m^4.
    """
    return SimplySupportedBeamSolver(
        member_id="B1",
        span_L=5.0,
        E=200e6, # kPa (kN/m2) -> 200 GPa
        I=0.0001
    )

@pytest.fixture
def portal_frame_setup():
    """
    Returns a GlobalMatrixSolver configured as a simple portal frame.
    Span: 6m, Height: 4m. Fixed at bases.
    """
    solver = GlobalMatrixSolver()
    E = 200e6
    A = 0.1
    I = 0.0005
    
    # Simple Portal Frame
    # n1 --- n2
    # |      |
    # n0     n3
    solver.add_node("n0", 0.0, 0.0, [True, True, True])
    solver.add_node("n1", 0.0, 4.0, [False, False, False])
    solver.add_node("n2", 6.0, 4.0, [False, False, False])
    solver.add_node("n3", 6.0, 0.0, [True, True, True])
    
    solver.add_element("c1", "n0", "n1", E, A, I)
    solver.add_element("b1", "n1", "n2", E, A, I)
    solver.add_element("c2", "n3", "n2", E, A, I)
    
    return solver
