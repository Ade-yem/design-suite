"""
Storeys-upstream audit fix (Workstream B, Slice 0).

Guards that storey extrapolation now happens BEFORE Gate-1 via
``file_service.apply_storeys`` — so the geometry the engineer verifies (and that
Gate-1 snapshots, by reading ``get_parsed``) is the true multi-storey model, and
the storey count is persisted on the project. Previously this happened during the
later loading stage, mutating already-audited geometry.
"""
from services.files import file_service
from storage.project_store import project_store
from schemas.project import ProjectCreate


def _single_floor_geometry() -> dict:
    return {
        "members": [
            {"member_id": "B1", "member_type": "beam",
             "meta": {"b_mm": 225, "h_mm": 450}, "spans_m": [5.0]},
            {"member_id": "C1", "member_type": "column",
             "meta": {"b_mm": 300, "h_mm": 300}},
        ],
        "layouts_processed": ["Model"],
        "scale": {"factor": 1.0, "unit": "mm", "confirmed": True},
    }


async def _new_project() -> str:
    proj = await project_store.create(ProjectCreate(name="Tower", reference="T-1"))
    return proj.project_id


async def test_apply_storeys_extrapolates_and_persists_before_gate1():
    pid = await _new_project()
    await file_service.register_geometry(pid, _single_floor_geometry())

    res = await file_service.apply_storeys(pid, num_storeys=3, storey_height_m=3.25)

    # 2 typical members × 3 storeys
    assert res["member_count"] == 6

    # What Gate-1 will snapshot (get_parsed) is the multi-storey set, all tagged.
    parsed = await file_service.get_parsed(pid)
    assert len(parsed["members"]) == 6
    assert all(m.get("storey") for m in parsed["members"])
    assert {m["storey"] for m in parsed["members"]} == {"L01", "L02", "L03"}

    # Persisted on the project so loading/analyst can read it without the dialogue.
    proj = await project_store.get(pid, bypass_tenant_check=True)
    assert proj.num_storeys == 3
    assert proj.storey_height_m == 3.25


async def test_apply_storeys_is_idempotent_rebuild():
    pid = await _new_project()
    await file_service.register_geometry(pid, _single_floor_geometry())

    await file_service.apply_storeys(pid, num_storeys=3, storey_height_m=3.0)
    # Re-running with a different count rebuilds from the cached typical floor,
    # it does not compound on the already-extrapolated members.
    res2 = await file_service.apply_storeys(pid, num_storeys=2, storey_height_m=3.0)

    assert res2["member_count"] == 4
    parsed = await file_service.get_parsed(pid)
    assert {m["storey"] for m in parsed["members"]} == {"L01", "L02"}


async def test_apply_storeys_single_storey_tags_l01():
    pid = await _new_project()
    await file_service.register_geometry(pid, _single_floor_geometry())

    res = await file_service.apply_storeys(pid, num_storeys=1, storey_height_m=3.0)

    assert res["member_count"] == 2
    parsed = await file_service.get_parsed(pid)
    # Even single-storey is uniformly tagged, so the loading-stage fallback's
    # "already extrapolated" guard recognises it and won't re-mutate.
    assert all(m.get("storey") == "L01" for m in parsed["members"])
