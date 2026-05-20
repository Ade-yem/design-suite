import pytest
from core.loading.assemblers import SlabLoadAssembler, BeamLoadAssembler
from models.loading.schema import DesignCode, OccupancyCategory


class TestSlabLoadAssembly:

    def test_solid_slab_self_weight(self):
        """175mm slab: SW = 0.175 × 25 = 4.375 kN/m², rounds to 4.38"""
        result = SlabLoadAssembler.assemble_slab_load(
            thickness_mm=175,
            screed_load=0.0, finishes_load=0.0, services_load=0.0,
            occupancy=OccupancyCategory.CUSTOM, custom_qk=0.0,
            code=DesignCode.BS8110
        )
        assert result["gk"] == pytest.approx(4.38, abs=1e-9)

    def test_superimposed_dead_loads_add_to_gk(self):
        """Superimposed DL (screed + finishes + services) accumulates in gk"""
        result = SlabLoadAssembler.assemble_slab_load(
            thickness_mm=200,
            screed_load=0.5, finishes_load=0.8, services_load=0.25,
            occupancy=OccupancyCategory.CUSTOM, custom_qk=0.0,
            code=DesignCode.BS8110
        )
        # SW = 0.2 × 25 = 5.0, plus 0.5 + 0.8 + 0.25 = 6.55
        assert result["gk"] == pytest.approx(6.55, abs=1e-9)

    def test_uls_load_is_factored(self):
        """uls_load = 1.4 × gk + 1.6 × qk (BS8110)"""
        result = SlabLoadAssembler.assemble_slab_load(
            thickness_mm=150,
            screed_load=0.0, finishes_load=0.0, services_load=0.0,
            occupancy=OccupancyCategory.CUSTOM, custom_qk=3.0,
            code=DesignCode.BS8110
        )
        expected_uls = round(1.4 * result["gk"] + 1.6 * result["qk"], 2)
        assert result["uls_load"] == pytest.approx(expected_uls, abs=1e-9)

    def test_one_way_classification_at_ratio_2(self):
        """ly/lx = 2.0 → one-way slab (boundary is inclusive)"""
        result = SlabLoadAssembler.classify_slab(ly=8.0, lx=4.0)
        assert result == "one-way"

    def test_two_way_classification_lylx_less_than_2(self):
        """ly/lx < 2.0 → two-way slab"""
        result = SlabLoadAssembler.classify_slab(ly=6.0, lx=4.5)
        assert result == "two-way"

    def test_one_way_ratio_well_above_2(self):
        """ly/lx = 3.0 → clearly one-way"""
        result = SlabLoadAssembler.classify_slab(ly=9.0, lx=3.0)
        assert result == "one-way"


class TestBeamLoadAssembly:

    def test_one_way_slab_short_span_beam_carries_no_load(self):
        """Short-span beam in a one-way slab: equivalent UDL is zero"""
        result = BeamLoadAssembler.equivalent_udl_from_slab(
            slab_gk_area=5.0, slab_qk_area=3.0,
            lx=4.0, ly=9.0, is_short_span_beam=True
        )
        assert result["equivalent_gk_m"] == pytest.approx(0.0)
        assert result["equivalent_qk_m"] == pytest.approx(0.0)

    def test_one_way_slab_long_span_beam_carries_tributary_load(self):
        """Long-span beam in one-way slab: eq_gk = gk_area × (lx/2)"""
        result = BeamLoadAssembler.equivalent_udl_from_slab(
            slab_gk_area=5.0, slab_qk_area=3.0,
            lx=4.0, ly=9.0, is_short_span_beam=False
        )
        assert result["equivalent_gk_m"] == pytest.approx(5.0 * 2.0, rel=1e-4)
        assert result["equivalent_qk_m"] == pytest.approx(3.0 * 2.0, rel=1e-4)

    def test_two_way_slab_short_span_beam_triangular_load(self):
        """Two-way slab, short-span beam: eq_gk = gk_area × (lx/3)"""
        result = BeamLoadAssembler.equivalent_udl_from_slab(
            slab_gk_area=6.0, slab_qk_area=3.0,
            lx=6.0, ly=7.0, is_short_span_beam=True
        )
        assert result["equivalent_gk_m"] == pytest.approx(6.0 * (6.0 / 3), rel=1e-4)
