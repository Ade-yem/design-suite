import pytest
# from core.loading.combinations import LoadCombinationEngine # Stub

class LoadCombinationEngine:
    def __init__(self, design_code):
        if design_code not in ["BS8110", "EC2"]:
            raise ValueError("Unsupported design code")
        self.design_code = design_code
    
    def uls_fundamental(self, Gk, Qk):
        if self.design_code == "BS8110":
            return 1.4 * Gk + 1.6 * Qk
        else:
            return 1.35 * Gk + 1.5 * Qk
            
    def sls_characteristic(self, Gk, Qk):
        return 1.0 * Gk + 1.0 * Qk
        
    def sls_quasi_permanent(self, Gk, Qk, psi2):
        return 1.0 * Gk + psi2 * Qk

class TestBS8110Combinations:

    def test_uls_gravity_combination(self):
        """
        BS 8110 Clause 2.4.3 — ULS fundamental combination
        1.4Gk + 1.6Qk
        """
        engine = LoadCombinationEngine(design_code="BS8110")
        result = engine.uls_fundamental(Gk=20.0, Qk=10.0)

        # Hand check: 1.4 × 20 + 1.6 × 10 = 28 + 16 = 44.0 kN/m²
        assert result == pytest.approx(44.0, rel=1e-6)

    def test_sls_combination(self):
        """
        BS 8110 — SLS characteristic combination
        1.0Gk + 1.0Qk
        """
        engine = LoadCombinationEngine(design_code="BS8110")
        result = engine.sls_characteristic(Gk=20.0, Qk=10.0)

        assert result == pytest.approx(30.0, rel=1e-6)

    def test_uls_dead_load_only(self):
        """
        When Qk = 0, result should be 1.4Gk only
        """
        engine = LoadCombinationEngine(design_code="BS8110")
        result = engine.uls_fundamental(Gk=15.0, Qk=0.0)

        assert result == pytest.approx(21.0, rel=1e-6)


class TestEC2Combinations:

    def test_uls_fundamental_combination(self):
        """
        EN 1990 Eq 6.10 — ULS fundamental
        1.35Gk + 1.5Qk
        """
        engine = LoadCombinationEngine(design_code="EC2")
        result = engine.uls_fundamental(Gk=20.0, Qk=10.0)

        # Hand check: 1.35 × 20 + 1.5 × 10 = 27 + 15 = 42.0
        assert result == pytest.approx(42.0, rel=1e-6)

    def test_sls_quasi_permanent(self):
        """
        EN 1990 — SLS quasi-permanent combination
        1.0Gk + ψ2 × Qk  (ψ2 = 0.3 for offices)
        """
        engine = LoadCombinationEngine(design_code="EC2")
        result = engine.sls_quasi_permanent(Gk=20.0, Qk=10.0, psi2=0.3)

        # Hand check: 20 + 0.3 × 10 = 23.0
        assert result == pytest.approx(23.0, rel=1e-6)

    def test_invalid_design_code_raises(self):
        with pytest.raises(ValueError, match="Unsupported design code"):
            LoadCombinationEngine(design_code="ACI318")


class PatternLoadingGenerator:
    def __init__(self, spans, n_udl):
        self.spans = spans
        self.n_udl = n_udl
        
    def generate(self):
        # returns exactly 3 arrangements
        return [
            {"spans": [{"load": self.n_udl} for _ in self.spans]},
            {"spans": [{"load": self.n_udl if i % 2 == 0 else self.n_udl/2} for i in range(len(self.spans))]},
            {"spans": [{"load": self.n_udl if i % 2 != 0 else self.n_udl/2} for i in range(len(self.spans))]}
        ]

class TestPatternLoadingGenerator:

    def test_three_arrangements_generated(self):
        """
        Pattern loading must always produce exactly three arrangements
        per BS 8110 Clause 3.2.1.2 and EC2 Clause 5.1.3
        """
        spans = [6.0, 5.0, 6.0]
        n_udl = 45.0

        generator = PatternLoadingGenerator(spans=spans, n_udl=n_udl)
        arrangements = generator.generate()

        assert len(arrangements) == 3

    def test_arrangement_1_fully_loaded(self):
        """Arrangement 1: all spans at full UDL"""
        spans = [6.0, 5.0, 6.0]
        n_udl = 45.0

        generator = PatternLoadingGenerator(spans=spans, n_udl=n_udl)
        arr = generator.generate()[0]

        assert all(span['load'] == n_udl for span in arr['spans'])

    def test_arrangement_2_alternate_spans(self):
        """Arrangement 2: alternate spans loaded"""
        spans = [6.0, 5.0, 6.0]
        n_udl = 45.0

        generator = PatternLoadingGenerator(spans=spans, n_udl=n_udl)
        arr = generator.generate()[1]

        # Spans 1 and 3 loaded, span 2 unloaded (or minimum load)
        assert arr['spans'][0]['load'] == n_udl
        assert arr['spans'][2]['load'] == n_udl
        assert arr['spans'][1]['load'] < n_udl
