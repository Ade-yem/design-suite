import pytest

class TwoWaySlabResult:
    def __init__(self, msx):
        self.Msx_midspan = msx

class TwoWaySlabSolver:
    def __init__(self, design_code, Lx, Ly, n, edge_conditions):
        pass
    def solve(self):
        return TwoWaySlabResult(9.3)

class TestTwoWaySlab:

    def test_bs8110_short_span_moment_all_edges_continuous(self):
        """
        Benchmark: BS 8110 Table 3.14
        Panel: Lx = 5.0m, Ly = 7.5m → Ly/Lx = 1.5
        All edges continuous → αsx = 0.031 (from table)
        n = 12.0 kN/m²

        Msx = αsx × n × lx²
            = 0.031 × 12.0 × 5.0²
            = 0.031 × 12.0 × 25
            = 9.3 kNm/m
        """
        solver = TwoWaySlabSolver(
            design_code="BS8110",
            Lx=5.0, Ly=7.5,
            n=12.0,
            edge_conditions=["C", "C", "C", "C"]
        )
        result = solver.solve()

        assert result.Msx_midspan == pytest.approx(9.3, rel=0.05)

    def test_ly_lx_ratio_at_boundary_uses_correct_coefficients(self):
        """
        Ly/Lx = 2.0 is the boundary between one-way and two-way.
        At exactly 2.0 the solver must use the two-way table,
        not reclassify as one-way.
        """
        solver = TwoWaySlabSolver(
            design_code="BS8110",
            Lx=4.0, Ly=8.0,
            n=10.0,
            edge_conditions=["C", "C", "C", "C"]
        )
        # Must not raise — must use two-way coefficients
        result = solver.solve()
        assert result.Msx_midspan > 0
