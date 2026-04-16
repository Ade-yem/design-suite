import pytest
from models.loading.schema import DesignCode, OccupancyCategory
from services.loading.assemblers import SlabLoadAssembler, BeamLoadAssembler
from services.analysis.beam_solver import SimplySupportedBeamSolver

def test_pipeline_slab_to_beam_analysis():
    """
    Integration Test:
    1. Solid Slab 200mm, 3m x 6m (One-Way)
    2. Supports on long sides (6m beams)
    3. Analyze 6m beam for equivalent UDL
    """
    # -- Step 1: Loading --
    # Gk: 5.0 (SW) + 1.0 (fin) = 6.0 kPa
    # Qk: 3.0 (Office)
    slab_loads = SlabLoadAssembler.assemble_slab_load(
        thickness_mm=200,
        screed_load=0.0,
        finishes_load=1.0,
        services_load=0.0,
        occupancy=OccupancyCategory.OFFICE,
        custom_qk=0.0,
        code=DesignCode.EC2
    )
    
    # -- Step 2: Distribution --
    # One-Way spanning onto 6m beam. Tributary width = Lx/2 = 3/2 = 1.5m
    beam_dist = BeamLoadAssembler.equivalent_udl_from_slab(
        slab_gk_area=slab_loads["gk"],
        slab_qk_area=slab_loads["qk"],
        lx=3.0,
        ly=6.0,
        is_short_span_beam=False
    )
    # eq_gk = 6.0 * 1.5 = 9.0 kN/m
    # eq_qk = 3.0 * 1.5 = 4.5 kN/m
    # Total design n_uls = 9.0*1.35 + 4.5*1.5 = 12.15 + 6.75 = 18.9 kN/m
    n_uls = 1.35 * beam_dist["equivalent_gk_m"] + 1.5 * beam_dist["equivalent_qk_m"]
    
    # -- Step 3: Analysis --
    # Analyze 6m beam with n_uls
    # M = 18.9 * 6^2 / 8 = 18.9 * 4.5 = 85.05 kNm
    solver = SimplySupportedBeamSolver(
        member_id="B1",
        span_L=6.0,
        E=30e6,
        I=0.001,
        design_code="EC2"
    )
    solver.add_udl(n_uls)
    analysis_result = solver.solve()
    
    # -- Step 4: Verification --
    assert analysis_result.stress_resultants.M_max_sagging_kNm == pytest.approx(85.05, abs=0.01)
    assert analysis_result.stress_resultants.V_max_kN == pytest.approx(18.9 * 3.0, abs=0.01) # nL/2
    assert "Applied Uniformly Distributed Load" in analysis_result.calculation_trace[0].description
