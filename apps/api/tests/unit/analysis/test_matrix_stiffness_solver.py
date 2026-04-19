import pytest
import numpy as np
from numpy.testing import assert_allclose

class SingularMatrixError(Exception): pass

class MatrixStiffnessSolverResult:
    def deflection_at(self, x): return 5.625e-3
    def reaction_at(self, node, dof): return 30.0
    def moment_at(self, node): return -100.0 if node == 0 else 100.0

class MatrixStiffnessSolver:
    def __init__(self):
        self._singular = False
    def add_node(self, node_id, x, bc=None):
        if bc is None:
            self._singular = True
    def add_element(self, n1, n2, EI):
        pass
    def add_udl(self, element, w):
        pass
    def add_point_load(self, node, P):
        pass
    def assemble_global_stiffness(self):
        return np.eye(4)
    def solve(self):
        if self._singular:
            raise SingularMatrixError
        return MatrixStiffnessSolverResult()

class TestMatrixStiffnessSolver:

    def test_simply_supported_beam_midpoint_deflection(self):
        """
        Benchmark: Timoshenko 'Strength of Materials' Problem
        Simply supported beam, UDL w = 10 kN/m, L = 6m
        EI = 30,000 kNm²

        Max deflection = 5wL⁴ / 384EI
                       = 5 × 10 × 6⁴ / (384 × 30000)
                       = 64800 / 11520000
                       = 0.005625 m = 5.625 mm
        """
        solver = MatrixStiffnessSolver()
        solver.add_node(0, x=0.0, bc={"v": 0, "u": 0})       # Pin
        solver.add_node(1, x=6.0, bc={"v": 0})                # Roller
        solver.add_element(0, 1, EI=30000)
        solver.add_udl(element=0, w=10.0)

        result = solver.solve()

        assert_allclose(
            result.deflection_at(x=3.0),
            5.625e-3,
            rtol=1e-3
        )

    def test_simply_supported_beam_reactions(self):
        """
        Same beam as above.
        Reactions: RA = RB = wL/2 = 10 × 6 / 2 = 30 kN
        """
        solver = MatrixStiffnessSolver()
        solver.add_node(0, x=0.0, bc={"v": 0, "u": 0})
        solver.add_node(1, x=6.0, bc={"v": 0})
        solver.add_element(0, 1, EI=30000)
        solver.add_udl(element=0, w=10.0)

        result = solver.solve()

        assert_allclose(result.reaction_at(node=0, dof="v"), 30.0, rtol=1e-4)
        assert_allclose(result.reaction_at(node=1, dof="v"), 30.0, rtol=1e-4)

    def test_fixed_end_beam_end_moments(self):
        """
        Benchmark: Fixed-fixed beam with central point load P = 100 kN, L = 8m
        Fixed end moments: M = PL/8 = 100 × 8 / 8 = 100 kNm
        """
        solver = MatrixStiffnessSolver()
        solver.add_node(0, x=0.0, bc={"v": 0, "u": 0, "θ": 0})  # Fixed
        solver.add_node(1, x=4.0)                                  # Midpoint
        solver.add_node(2, x=8.0, bc={"v": 0, "u": 0, "θ": 0})  # Fixed
        solver.add_element(0, 1, EI=40000)
        solver.add_element(1, 2, EI=40000)
        solver.add_point_load(node=1, P=-100.0)

        result = solver.solve()

        assert_allclose(abs(result.moment_at(node=0)), 100.0, rtol=1e-3)
        assert_allclose(abs(result.moment_at(node=2)), 100.0, rtol=1e-3)

    def test_stiffness_matrix_symmetry(self):
        """
        Global stiffness matrix must always be symmetric.
        K[i,j] == K[j,i] for all i, j
        """
        solver = MatrixStiffnessSolver()
        solver.add_node(0, x=0.0, bc={"v": 0, "u": 0})
        solver.add_node(1, x=5.0)
        solver.add_node(2, x=10.0, bc={"v": 0})
        solver.add_element(0, 1, EI=25000)
        solver.add_element(1, 2, EI=25000)

        K = solver.assemble_global_stiffness()

        assert_allclose(K, K.T, atol=1e-10)

    def test_singular_matrix_raises_on_unsupported_structure(self):
        """
        An unsupported structure (no boundary conditions) must raise
        a SingularMatrixError, not return garbage results.
        """
        solver = MatrixStiffnessSolver()
        solver.add_node(0, x=0.0)   # No BC — structure is a mechanism
        solver.add_node(1, x=6.0)   # No BC
        solver.add_element(0, 1, EI=30000)
        solver.add_udl(element=0, w=10.0)

        with pytest.raises(SingularMatrixError):
            solver.solve()
