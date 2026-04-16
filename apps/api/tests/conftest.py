import pytest
import numpy as np
from services.analysis.global_solver import GlobalMatrixSolver
from services.analysis.beam_solver import SimplySupportedBeamSolver

@pytest.fixture
def empty_solver():
    """Returns a fresh GlobalMatrixSolver instance."""
    return GlobalMatrixSolver()

@pytest.fixture
def portal_frame_setup(empty_solver):
    """
    Sets up a standard portal frame:
    - 2 fixed bases at (0,0) and (5,0)
    - 2 beam-column nodes at (0,4) and (5,4)
    - Column properties: E=200e9, A=0.01, I=0.0001
    """
    E = 200e9
    A = 0.01
    I = 0.0001
    
    empty_solver.add_node("n0", 0.0, 0.0, [True, True, True])
    empty_solver.add_node("n1", 0.0, 4.0, [False, False, False])
    empty_solver.add_node("n2", 5.0, 4.0, [False, False, False])
    empty_solver.add_node("n3", 5.0, 0.0, [True, True, True])
    
    empty_solver.add_element("col_left", "n0", "n1", E, A, I)
    empty_solver.add_element("beam", "n1", "n2", E, A, I)
    empty_solver.add_element("col_right", "n2", "n3", E, A, I)
    
    return empty_solver

@pytest.fixture
def simply_supported_beam():
    """Returns a 5m simply supported beam fixture."""
    # E = 30 GPa (RC), I = 0.001 m4
    return SimplySupportedBeamSolver(
        member_id="B1",
        span_L=5.0,
        E=30e6, # kPa
        I=0.001, # m4
        design_code="EC2"
    )
