import pytest
from models.loading.schema import DesignCode, OccupancyCategory
from services.loading.assemblers import SlabLoadAssembler, BeamLoadAssembler
from services.loading.special_slabs import RibbedSlabAssembler

def test_slab_classification():
    """Verify one-way vs two-way classification."""
    assert SlabLoadAssembler.classify_slab(ly=5.0, lx=2.0) == "one-way"  # ratio = 2.5
    assert SlabLoadAssembler.classify_slab(ly=4.0, lx=3.0) == "two-way"  # ratio = 1.33
    with pytest.raises(ValueError):
        SlabLoadAssembler.classify_slab(ly=5.0, lx=0)

def test_slab_load_assembly():
    """Verify Gk, Qk calculation for solid slab."""
    # 200mm slab (5.0 kPa SW), 1.0 screed, 0.5 finishes, 0.5 services = 7.0 kPa Gk
    # Office Qk (EC2) = 3.0 kPa
    # ULS = 1.35*7.0 + 1.5*3.0 = 9.45 + 4.5 = 13.95
    res = SlabLoadAssembler.assemble_slab_load(
        thickness_mm=200,
        screed_load=1.0,
        finishes_load=0.5,
        services_load=0.5,
        occupancy=OccupancyCategory.OFFICE,
        custom_qk=0.0,
        code=DesignCode.EC2
    )
    assert res["gk"] == 7.0
    assert res["qk"] == 3.0
    assert res["uls_load"] == 13.95

def test_beam_equivalent_udl():
    """Verify triangular distribution for two-way short span."""
    # Two-way 3m x 4m, short span beam (3m)
    # Load = 10 kPa
    # Eq UDL = 10 * 3 / 3 = 10 kN/m
    res = BeamLoadAssembler.equivalent_udl_from_slab(
        slab_gk_area=10.0,
        slab_qk_area=5.0,
        lx=3.0,
        ly=4.0,
        is_short_span_beam=True
    )
    assert res["equivalent_gk_m"] == 10.0
    assert res["equivalent_qk_m"] == 5.0

def test_ribbed_slab_weight():
    """Verify weight calculation for ribbed slab."""
    # 50mm topping, 150x250 ribs at 600 centers
    # Topping: 0.05 * 25 = 1.25 kPa
    # Ribs: (0.15 * 0.25) * (1 / 0.6) * 25 = 0.0375 * 1.666 * 25 = 1.5625 kPa
    # Total = 2.8125 kPa
    sw = RibbedSlabAssembler.calculate_self_weight(
        topping_thickness_mm=50,
        rib_width_mm=150,
        rib_depth_below_topping_mm=250,
        rib_spacing_mm=600
    )
    assert pytest.approx(sw, abs=0.01) == 2.81
