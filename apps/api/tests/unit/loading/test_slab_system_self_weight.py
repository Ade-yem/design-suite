"""
Slab-system-aware self-weight in the loading engine (Workstream B, Slice 1).

The engineer's choice of slab structural system (solid / ribbed / waffle / flat)
must drive *loading*, not just design: ribbed/waffle slabs are lighter than an
equivalent solid slab. This wires the previously-dead load assemblers into the
per-member self-weight used by ``LoadingService._run_engine``.
"""
from services.loading import _member_self_weight_kNm2


def _slab(system: str, **geom) -> dict:
    return {"member_type": "slab", "meta": {"slab_system": system, "h_mm": 300, **geom}}


def test_solid_slab_self_weight_is_full_thickness_plate():
    # 300 mm × 25 kN/m³ = 7.5 kN/m²
    assert _member_self_weight_kNm2(_slab("solid")) == 7.5


def test_ribbed_slab_is_lighter_than_solid():
    solid = _member_self_weight_kNm2(_slab("solid"))
    ribbed = _member_self_weight_kNm2(
        _slab("ribbed", topping_thickness=75, rib_width=125, rib_spacing=700)
    )
    assert 0 < ribbed < solid


def test_waffle_slab_also_lighter_than_solid():
    solid = _member_self_weight_kNm2(_slab("solid"))
    waffle = _member_self_weight_kNm2(
        _slab("waffle", topping_thickness=75, rib_width=125, rib_spacing=700)
    )
    assert 0 < waffle < solid


def test_flat_slab_is_full_plate_like_solid():
    assert _member_self_weight_kNm2(_slab("flat")) == _member_self_weight_kNm2(_slab("solid"))


def test_staircase_self_weight_is_positive():
    stair = {"member_type": "staircase", "meta": {"tread": 250, "riser": 175, "waist": 150}}
    assert _member_self_weight_kNm2(stair) > 0


def test_other_member_types_contribute_no_slab_self_weight():
    # Beam/column self-weight is handled elsewhere (designer loop / takedown).
    assert _member_self_weight_kNm2({"member_type": "beam", "meta": {"b_mm": 300, "h_mm": 500}}) == 0.0
    assert _member_self_weight_kNm2({"member_type": "column", "meta": {"b_mm": 400, "h_mm": 400}}) == 0.0
