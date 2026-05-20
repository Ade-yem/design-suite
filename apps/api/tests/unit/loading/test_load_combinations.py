import pytest
from core.loading.load_combinations import LoadCombinationEngine
from models.loading.schema import DesignCode, LimitState


class TestBS8110Combinations:

    def test_uls_gravity_combination(self):
        """BS 8110 Clause 2.4.3 — 1.4Gk + 1.6Qk"""
        result = LoadCombinationEngine.factor_loads(
            gk=20.0, qk=10.0, wk=0.0,
            code=DesignCode.BS8110, limit_state=LimitState.ULS_DOMINANT
        )
        assert result == pytest.approx(44.0, rel=1e-6)

    def test_sls_combination(self):
        """BS 8110 SLS characteristic — 1.0Gk + 1.0Qk"""
        result = LoadCombinationEngine.factor_loads(
            gk=20.0, qk=10.0, wk=0.0,
            code=DesignCode.BS8110, limit_state=LimitState.SLS_CHARACTERISTIC
        )
        assert result == pytest.approx(30.0, rel=1e-6)

    def test_uls_dead_load_only(self):
        """When Qk = 0, result should be 1.4Gk only"""
        result = LoadCombinationEngine.factor_loads(
            gk=15.0, qk=0.0, wk=0.0,
            code=DesignCode.BS8110, limit_state=LimitState.ULS_DOMINANT
        )
        assert result == pytest.approx(21.0, rel=1e-6)

    def test_get_factors_returns_correct_tuple(self):
        """get_factors returns (gamma_G, gamma_Q, gamma_W) for BS8110 ULS"""
        gamma_G, gamma_Q, gamma_W = LoadCombinationEngine.get_factors(
            DesignCode.BS8110, LimitState.ULS_DOMINANT
        )
        assert gamma_G == pytest.approx(1.4)
        assert gamma_Q == pytest.approx(1.6)
        assert gamma_W == pytest.approx(0.0)


class TestEC2Combinations:

    def test_uls_fundamental_combination(self):
        """EN 1990 Eq 6.10 — 1.35Gk + 1.5Qk"""
        result = LoadCombinationEngine.factor_loads(
            gk=20.0, qk=10.0, wk=0.0,
            code=DesignCode.EC2, limit_state=LimitState.ULS_DOMINANT
        )
        assert result == pytest.approx(42.0, rel=1e-6)

    def test_sls_quasi_permanent(self):
        """EN 1990 SLS quasi-permanent — 1.0Gk + 0.3Qk"""
        result = LoadCombinationEngine.factor_loads(
            gk=20.0, qk=10.0, wk=0.0,
            code=DesignCode.EC2, limit_state=LimitState.SLS_QUASI_PERMANENT
        )
        assert result == pytest.approx(23.0, rel=1e-6)

    def test_invalid_design_code_raises(self):
        """An unknown design code string must raise ValueError"""
        with pytest.raises(ValueError):
            DesignCode("ACI318")


class TestPatternLoadingGenerator:

    def test_three_arrangements_generated(self):
        """Pattern loading must produce exactly three arrangements"""
        result = LoadCombinationEngine.generate_pattern_loads(
            gk=20.0, qk=10.0, code=DesignCode.BS8110
        )
        assert len(result["arrangements"]) == 3

    def test_arrangement_1_is_fully_loaded(self):
        """First arrangement name: all spans fully loaded"""
        result = LoadCombinationEngine.generate_pattern_loads(
            gk=20.0, qk=10.0, code=DesignCode.BS8110
        )
        assert result["arrangements"][0]["name"] == "All spans fully loaded"

    def test_arrangement_2_is_alternate_spans(self):
        """Second arrangement name: alternate spans loaded"""
        result = LoadCombinationEngine.generate_pattern_loads(
            gk=20.0, qk=10.0, code=DesignCode.BS8110
        )
        assert result["arrangements"][1]["name"] == "Alternate spans loaded"

    def test_max_load_greater_than_min_load(self):
        """ULS max load must exceed dead-load-only minimum"""
        result = LoadCombinationEngine.generate_pattern_loads(
            gk=20.0, qk=10.0, code=DesignCode.BS8110
        )
        assert result["max_load"] > result["min_load"]

    def test_max_load_equals_uls_factored(self):
        """max_load = 1.4Gk + 1.6Qk for BS8110"""
        result = LoadCombinationEngine.generate_pattern_loads(
            gk=20.0, qk=10.0, code=DesignCode.BS8110
        )
        expected = 1.4 * 20.0 + 1.6 * 10.0
        assert result["max_load"] == pytest.approx(expected, rel=1e-6)
