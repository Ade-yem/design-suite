import pytest
import numpy as np
from numpy.testing import assert_allclose
from core.analysis.global_solver import GlobalMatrixSolver


class TestGlobalMatrixSolver:

    def test_simply_supported_beam_midpoint_deflection(self):
        """
        Timoshenko benchmark: δ_max = 5wL⁴/384EI
        w=10 kN/m, L=6m, EI=30000 kNm² → δ = 5.625e-3 m
        """
        solver = GlobalMatrixSolver()
        solver.add_node("A", 0.0, 0.0, [True, True, False])   # pin
        solver.add_node("M", 3.0, 0.0, [False, False, False]) # midpoint (free)
        solver.add_node("B", 6.0, 0.0, [False, True, False])  # roller
        solver.add_element("E1", "A", "M", E=30000, A=1.0, I=1.0)
        solver.add_element("E2", "M", "B", E=30000, A=1.0, I=1.0)
        solver.add_member_udl("E1", w=-10.0)
        solver.add_member_udl("E2", w=-10.0)

        result = solver.solve()

        # Node M is index 1 → DOFs [3, 4, 5]; vertical = DOF 4
        v_mid = result["displacements"][4]
        assert_allclose(v_mid, -5.625e-3, rtol=1e-3)

    def test_simply_supported_beam_reactions(self):
        """RA = RB = wL/2 = 10 × 6 / 2 = 30 kN"""
        solver = GlobalMatrixSolver()
        solver.add_node("A", 0.0, 0.0, [True, True, False])
        solver.add_node("B", 6.0, 0.0, [False, True, False])
        solver.add_element("E1", "A", "B", E=30000, A=1.0, I=1.0)
        solver.add_member_udl("E1", w=-10.0)

        result = solver.solve()

        assert_allclose(result["reactions"]["A"]["Fy"], 30.0, rtol=1e-4)
        assert_allclose(result["reactions"]["B"]["Fy"], 30.0, rtol=1e-4)

    def test_stiffness_matrix_symmetry(self):
        """Global stiffness matrix must satisfy K[i,j] == K[j,i] for all i, j"""
        solver = GlobalMatrixSolver()
        solver.add_node("A", 0.0, 0.0, [True, True, False])
        solver.add_node("M", 3.0, 0.0, [False, False, False])
        solver.add_node("B", 6.0, 0.0, [False, True, False])
        solver.add_element("E1", "A", "M", E=30000, A=1.0, I=1.0)
        solver.add_element("E2", "M", "B", E=30000, A=1.0, I=1.0)

        solver._assign_dofs()
        solver._assemble_global_system()
        K = solver.K_global

        assert_allclose(K, K.T, atol=1e-10)

    def test_singular_matrix_raises_on_unsupported_structure(self):
        """Structure with no boundary conditions must raise ValueError"""
        solver = GlobalMatrixSolver()
        solver.add_node("A", 0.0, 0.0, [False, False, False])
        solver.add_node("B", 6.0, 0.0, [False, False, False])
        solver.add_element("E1", "A", "B", E=30000, A=1.0, I=1.0)
        solver.add_member_udl("E1", w=-10.0)

        with pytest.raises(ValueError):
            solver.solve()

    def test_nodal_load_vertical_reaction(self):
        """Cantilever with tip point load: RA_vertical = P"""
        solver = GlobalMatrixSolver()
        solver.add_node("A", 0.0, 0.0, [True, True, True])  # fixed
        solver.add_node("B", 4.0, 0.0, [False, False, False])
        solver.add_element("E1", "A", "B", E=30000, A=1.0, I=1.0)
        solver.apply_nodal_load("B", Fy=-50.0)

        result = solver.solve()

        assert_allclose(result["reactions"]["A"]["Fy"], 50.0, rtol=1e-4)
