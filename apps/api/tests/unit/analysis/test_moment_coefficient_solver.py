import pytest
from core.analysis.beam_solver import MomentCoefficientSolver


class TestMomentCoefficientSolver:

    def test_bs8110_end_span_midspan_moment(self):
        """
        BS 8110 Table 3.5 — end-span sagging:
        F = 45 × 6 = 270 kN, M = 0.090 × 270 × 6 = 145.8 kNm
        """
        solver = MomentCoefficientSolver(
            member_id="B-01", spans=[6.0, 6.0, 6.0], design_code="BS8110"
        )
        result = solver.solve(ultimate_load_kN_per_m=45.0)

        assert result.stress_resultants.M_max_sagging_kNm == pytest.approx(145.8, rel=1e-3)

    def test_bs8110_first_interior_support_moment(self):
        """
        BS 8110 Table 3.5 — first interior support hogging:
        M = -0.100 × 270 × 6 = -162.0 kNm
        """
        solver = MomentCoefficientSolver(
            member_id="B-01", spans=[6.0, 6.0, 6.0], design_code="BS8110"
        )
        result = solver.solve(ultimate_load_kN_per_m=45.0)

        assert result.stress_resultants.M_max_hogging_kNm == pytest.approx(-162.0, rel=1e-3)

    def test_shear_force_at_support(self):
        """
        BS 8110 — end-span shear at inner support: V = 0.60 × F
        F = 45 × 6 = 270 kN, V_inner = 162.0 kN
        """
        solver = MomentCoefficientSolver(
            member_id="B-01", spans=[6.0, 6.0, 6.0], design_code="BS8110"
        )
        result = solver.solve(ultimate_load_kN_per_m=45.0)

        assert result.stress_resultants.V_max_kN == pytest.approx(162.0, rel=1e-3)

    def test_result_metadata(self):
        """Result carries correct member_id, member_type, and analysis_method"""
        solver = MomentCoefficientSolver(
            member_id="B-03", spans=[5.0, 5.0], design_code="BS8110"
        )
        result = solver.solve(ultimate_load_kN_per_m=30.0)

        assert result.member_id == "B-03"
        assert result.member_type == "beam"
        assert result.analysis_method == "coefficients"

    def test_longer_spans_produce_larger_moments(self):
        """Increasing span length must increase sagging moment (all else equal)"""
        short = MomentCoefficientSolver("B-01", [5.0, 5.0, 5.0], "BS8110")
        long = MomentCoefficientSolver("B-01", [7.0, 7.0, 7.0], "BS8110")

        m_short = short.solve(40.0).stress_resultants.M_max_sagging_kNm
        m_long = long.solve(40.0).stress_resultants.M_max_sagging_kNm

        assert m_long > m_short

    def test_higher_load_produces_larger_moments(self):
        """Doubling the design UDL must double the moments (linear relationship)"""
        solver = MomentCoefficientSolver("B-01", [6.0, 6.0, 6.0], "BS8110")

        m_base = solver.solve(30.0).stress_resultants.M_max_sagging_kNm
        m_double = solver.solve(60.0).stress_resultants.M_max_sagging_kNm

        assert m_double == pytest.approx(2 * m_base, rel=1e-6)
