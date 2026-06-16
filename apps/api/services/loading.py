"""
services/loading.py
===================
Loading service — owns load definitions and combination output for a project.

Both the FastAPI loading router and the Analyst Agent call this service
directly; neither holds its own in-memory store.

Public API
----------
loading_service.define(project_id, definition)              → dict
loading_service.get_definition(project_id)                  → dict
loading_service.validate(definition)                        → LoadValidationResult
loading_service.run_combinations(project_id)                → dict
loading_service.get_output(project_id)                      → dict
loading_service.update_member_loads(project_id, mid, upd)   → dict
loading_service.clear(project_id)                           → None
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from schemas.loading import LoadValidationResult
from schemas.project import ProjectStatus
from storage.project_store import project_store

logger = logging.getLogger(__name__)


def _member_self_weight_kNm2(member: dict) -> float:
    """
    Structural self-weight (kN/m²) of a slab or staircase member, differentiated
    by the slab **structural system** the engineer chose.

    This is what lets the slab-system choice drive loading (not just design):
    ribbed/waffle slabs are lighter than an equivalent solid slab, flat slabs are
    a full plate. Self-weight is computed via the (previously unused) load
    assemblers in ``core/loading``. Other member types return 0 here — column
    self-weight is added in the takedown, beams converge via the designer loop.
    """
    member_type = str(member.get("member_type", "")).lower()
    geom = member.get("meta", {}) or {}

    from core.loading.tables import MaterialWeightTable

    if member_type == "slab":
        system = str(geom.get("slab_system") or "solid").lower().strip()
        h = float(geom.get("h_mm") or geom.get("h") or 0.0)
        if system in ("ribbed", "waffle"):
            from core.loading.special_slabs import RibbedSlabAssembler

            topping = float(geom.get("topping_thickness") or geom.get("topping_thickness_mm") or 75.0)
            rib_width = float(geom.get("rib_width") or geom.get("rib_width_mm") or 125.0)
            rib_spacing = float(geom.get("rib_spacing") or geom.get("rib_spacing_mm") or 700.0)
            rib_depth = max(h - topping, 0.0)
            return RibbedSlabAssembler.calculate_self_weight(
                topping, rib_width, rib_depth, rib_spacing
            )
        # solid / flat → full-thickness plate
        return (h / 1000.0) * MaterialWeightTable.get_rc_weight() if h else 0.0

    if member_type == "staircase":
        from core.loading.staircase import StaircaseLoadAssembler

        going = float(geom.get("tread") or geom.get("going_mm") or geom.get("tread_mm") or 250.0)
        riser = float(geom.get("riser") or geom.get("riser_mm") or 175.0)
        waist = float(geom.get("waist") or geom.get("waist_mm") or geom.get("h_mm") or 150.0)
        return StaircaseLoadAssembler.calculate_self_weight(going, riser, waist)

    return 0.0


# ── In-memory stores ──────────────────────────────────────────────────────────

class _LoadingStore:
    """
    In-memory store for load definitions and combination output.
    Delegates to stage_result_store.
    """

    def __init__(self) -> None:
        pass

    def set_definition(self, project_id: str, data: dict) -> None:
        """Store load definition for a project."""
        from storage.stage_result_store import stage_result_store
        payload = stage_result_store._memory_store.setdefault((project_id, "loads"), {})
        payload["definition"] = data

    def get_definition(self, project_id: str) -> Optional[dict]:
        """Return load definition or None."""
        from storage.stage_result_store import stage_result_store
        return stage_result_store._memory_store.get((project_id, "loads"), {}).get("definition")

    def set_output(self, project_id: str, data: dict) -> None:
        """Store combination output for a project."""
        from storage.stage_result_store import stage_result_store
        payload = stage_result_store._memory_store.setdefault((project_id, "loads"), {})
        payload["output"] = data

    def get_output(self, project_id: str) -> Optional[dict]:
        """Return combination output or None."""
        from storage.stage_result_store import stage_result_store
        return stage_result_store._memory_store.get((project_id, "loads"), {}).get("output")

    def clear(self, project_id: str) -> None:
        """Remove all loading data for a project."""
        from storage.stage_result_store import stage_result_store
        stage_result_store._memory_store.pop((project_id, "loads"), None)


_store = _LoadingStore()


# ── Service class ─────────────────────────────────────────────────────────────

class LoadingService:
    """
    Load definition and combination service.

    Wraps the ``core.loading`` combination engine and the loading store.
    Agents and routers call this service — they never perform load arithmetic
    themselves.
    """

    async def define(self, project_id: str, definition: dict) -> dict:
        """
        Persist a load definition for a project.

        Does NOT run the combination engine — call ``run_combinations`` next.

        Parameters
        ----------
        project_id : str
        definition : dict
            Validated payload matching ``LoadDefinitionRequest``.

        Returns
        -------
        dict
            ``{project_id, status, design_code, occupancy_category, created_at}``
        """
        _store.set_definition(project_id, definition)
        await project_store.save_loads(project_id, definition, None)
        logger.info(
            "Load definition stored for project %s. Code: %s, Occupancy: %s.",
            project_id,
            definition.get("design_code", "?"),
            definition.get("occupancy_category", "?"),
        )
        return {
            "project_id": project_id,
            "status": "accepted",
            "design_code": definition.get("design_code"),
            "occupancy_category": definition.get("occupancy_category"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_definition(self, project_id: str) -> dict:
        """
        Return the stored load definition for a project.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict
            Load definition dict, or empty dict if none stored.
        """
        return _store.get_definition(project_id) or {}

    def imposed_load_for(
        self, occupancy_category: str, design_code: str
    ) -> Optional[float]:
        """
        Derive the characteristic imposed floor load Qk (kN/m²) from occupancy.

        Wraps the ``core.loading`` occupancy table so the Analyst Agent can map a
        building's usage (e.g. "office") to a code-compliant Qk without performing
        the lookup itself.  Returns ``None`` for the ``custom`` category (or any
        unknown value), signalling that an explicit Qk must be supplied.

        Parameters
        ----------
        occupancy_category : str
            One of the ``OccupancyCategory`` values.
        design_code : str
            ``"BS8110"`` or ``"EC2"``.

        Returns
        -------
        float | None
            Characteristic imposed load in kN/m², or ``None`` if it cannot be
            derived from the table.
        """
        from core.loading.tables import OccupancyLoadTable
        from models.loading.schema import OccupancyCategory, DesignCode

        try:
            occ = OccupancyCategory(occupancy_category)
            code = DesignCode(design_code)
            return OccupancyLoadTable.get_load(occ, code)
        except (ValueError, KeyError):
            return None

    def validate(self, definition: dict) -> LoadValidationResult:
        """
        Validate a load definition without persisting it.

        Parameters
        ----------
        definition : dict
            Load definition payload.

        Returns
        -------
        LoadValidationResult
            ``{valid, errors, warnings}``
        """
        errors: list[str] = []
        warnings: list[str] = []

        imposed = definition.get("imposed_loads", {})
        floor_qk = imposed.get("floor_qk_kNm2", 0)
        if not floor_qk:
            errors.append("imposed_loads.floor_qk_kNm2: must be > 0.")
        if floor_qk > 10:
            warnings.append(
                f"floor_qk_kNm2 = {floor_qk} kN/m² is unusually high — please verify."
            )

        dead = definition.get("dead_loads", {})
        total_dead = sum([
            dead.get("finishes_kNm2", 0),
            dead.get("screed_kNm2", 0),
            dead.get("services_kNm2", 0),
            dead.get("partitions_kNm2", 0),
        ])
        if total_dead > 8:
            warnings.append(
                f"Total superimposed dead load = {total_dead:.2f} kN/m² — exceptionally high."
            )

        return LoadValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    async def run_combinations(self, project_id: str) -> dict:
        """
        Run the load combination engine for all registered members.

        Reads the stored load definition and the parsed geometry from
        ``services.files``.  Advances the project to ``LOADING_DEFINED``.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict
            Full loading output with factored ULS and SLS loads per member.

        Raises
        ------
        ValueError
            If no load definition has been submitted for this project.
        """
        await self.ensure_cached(project_id)
        definition = _store.get_definition(project_id)
        if not definition:
            raise ValueError(
                f"No load definition for project '{project_id}'. "
                "Submit a load definition first."
            )

        output = await self._run_engine(project_id, definition)
        _store.set_output(project_id, output)
        await project_store.advance_status(project_id, ProjectStatus.LOADING_DEFINED)
        await project_store.save_loads(project_id, definition, output)

        logger.info(
            "Load combinations computed for project %s: %d member(s), code=%s.",
            project_id,
            len(output.get("members", [])),
            definition.get("design_code", "?"),
        )
        return output

    def get_output(self, project_id: str) -> dict:
        """
        Return the factored load output produced by the combination engine.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict
            Combination output.

        Raises
        ------
        KeyError
            If combinations have not been run yet.
        """
        output = _store.get_output(project_id)
        if output is None:
            raise KeyError(
                f"No load output for project '{project_id}'. "
                "Run combinations first."
            )
        return output

    async def update_member_loads(
        self,
        project_id: str,
        member_id: str,
        dead_extra_kNm2: Optional[float] = None,
        imposed_override_kNm2: Optional[float] = None,
        notes: str = "",
    ) -> dict:
        """
        Apply a per-member load override to the stored definition.

        Parameters
        ----------
        project_id : str
        member_id : str
        dead_extra_kNm2 : float | None
        imposed_override_kNm2 : float | None
        notes : str

        Returns
        -------
        dict
            The applied override record.
        """
        definition = _store.get_definition(project_id) or {}
        overrides: list[dict] = definition.setdefault("member_overrides", [])

        existing = next((o for o in overrides if o.get("member_id") == member_id), None)
        if existing:
            if dead_extra_kNm2 is not None:
                existing["dead_extra_kNm2"] = dead_extra_kNm2
            if imposed_override_kNm2 is not None:
                existing["imposed_override_kNm2"] = imposed_override_kNm2
            existing["notes"] = notes
            result = existing
        else:
            entry: dict = {"member_id": member_id, "notes": notes}
            if dead_extra_kNm2 is not None:
                entry["dead_extra_kNm2"] = dead_extra_kNm2
            if imposed_override_kNm2 is not None:
                entry["imposed_override_kNm2"] = imposed_override_kNm2
            overrides.append(entry)
            result = entry

        _store.set_definition(project_id, definition)
        output = _store.get_output(project_id)
        await project_store.save_loads(project_id, definition, output)
        logger.info("Load override applied to member %s in project %s.", member_id, project_id)
        return result

    def clear(self, project_id: str) -> None:
        """
        Remove all loading data for a project.

        Parameters
        ----------
        project_id : str
        """
        _store.clear(project_id)

    # ── DB persistence helpers ────────────────────────────────────────────────

    async def ensure_cached(self, project_id: str) -> None:
        """Load load definitions and output from DB/store into cache if missing."""
        if _store.get_definition(project_id) and _store.get_output(project_id):
            return
        try:
            definition, output = await project_store.get_loads(project_id)
            if definition:
                _store.set_definition(project_id, definition)
            if output:
                _store.set_output(project_id, output)
        except Exception as exc:
            logger.warning("Project store load fetch for project %s failed: %s", project_id, exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run_engine(self, project_id: str, definition: dict) -> dict:
        """
        Orchestrate the core loading engine for all project members.

        Reads geometry from ``services.files`` (imported lazily to avoid
        circular imports at module load time).

        Parameters
        ----------
        project_id : str
        definition : dict

        Returns
        -------
        dict
            Full loading output.
        """
        from core.loading import LoadCombinationEngine, LoadSerializer
        from models.loading.schema import DesignCode, LimitState
        # Lazy import avoids circular dependency with services.files
        from services.files import file_service

        design_code_str = definition.get("design_code", "BS8110")
        design_code = DesignCode.BS8110 if design_code_str == "BS8110" else DesignCode.EC2

        dead = definition.get("dead_loads", {})
        imposed = definition.get("imposed_loads", {})

        gk_base = sum([
            dead.get("finishes_kNm2", 1.5),
            dead.get("screed_kNm2", 0.8),
            dead.get("services_kNm2", 0.5),
            dead.get("partitions_kNm2", 1.0),
        ])
        qk_base: float = imposed.get("floor_qk_kNm2", 2.5)
        cladding_gk = float(dead.get("cladding_kNm", 0.0))

        combo_label = (
            "1.4Gk + 1.6Qk" if design_code == DesignCode.BS8110 else "1.35Gk + 1.5Qk"
        )

        overrides: dict[str, dict] = {
            o["member_id"]: o for o in definition.get("member_overrides", [])
        }

        # Pull geometry from the files service
        try:
            parsed = await file_service.get_parsed(project_id)
        except KeyError:
            parsed = {}

        # Storey extrapolation now happens BEFORE Gate-1 (file_service.apply_storeys)
        # so the audited geometry matches the working geometry. This block is a
        # no-regression fallback for projects that never hit that path: it only
        # runs when the geometry has not already been extrapolated (no member
        # carries a `storey` tag), and it never re-mutates a verified model.
        already_extrapolated = bool(parsed) and any(
            m.get("storey") for m in parsed.get("members", [])
        )
        if parsed and not already_extrapolated:
            # Prefer the storeys persisted on the project; fall back to the
            # LangGraph project_parameters for older threads.
            num_storeys = 1
            storey_height_m = 3.0
            try:
                proj = await project_store.get(project_id, bypass_tenant_check=True)
                if proj:
                    num_storeys = getattr(proj, "num_storeys", 1) or 1
                    storey_height_m = getattr(proj, "storey_height_m", 3.0) or 3.0
            except Exception as exc:
                logger.warning("Failed to read storeys from project: %s", exc)
            if num_storeys == 1:
                try:
                    from agents.graph import app as graph_app
                    config = {"configurable": {"thread_id": project_id}}
                    state = await graph_app.aget_state(config)
                    if state and state.values:
                        params = state.values.get("project_parameters") or {}
                        num_storeys = params.get("num_storeys", num_storeys)
                        storey_height_m = params.get("storey_height_m", storey_height_m)
                except Exception as exc:
                    logger.warning("Failed to retrieve project parameters from state: %s", exc)

            # Store the original typical members if we haven't already
            if "typical_members" not in parsed:
                import copy
                parsed["typical_members"] = copy.deepcopy(parsed.get("members", []))

            # Run extrapolation
            from core.parsing.storey_generator import extrapolate_storeys
            layouts = parsed.get("layouts_processed") or ["Model"]
            extrapolated = extrapolate_storeys(
                typical_members=parsed["typical_members"],
                num_storeys=num_storeys,
                storey_height_m=storey_height_m,
                layouts_processed=layouts,
            )

            # Check if we actually mutated / updated the members list
            parsed["members"] = extrapolated
            await file_service.register_geometry(project_id, parsed)

            new_mids = [m["member_id"] for m in extrapolated if m.get("member_id")]
            await project_store.register_members_batch(project_id, new_mids)

            # Also update the LangGraph state so other agents/views see the extrapolated geometry
            try:
                from agents.graph import app as graph_app
                config = {"configurable": {"thread_id": project_id}}
                await graph_app.aupdate_state(config, {"parsed_structural_json": parsed})
            except Exception as exc:
                logger.warning("Failed to update LangGraph state with extrapolated geometry: %s", exc)

        parsed_members: dict[str, dict] = {}
        if parsed:
            parsed_members = {
                m["member_id"]: m for m in parsed.get("members", [])
            }

        member_ids = await project_store.get_member_ids(project_id)
        effective_ids = member_ids or list(parsed_members.keys())

        members_output: list[dict] = []
        for member_id in effective_ids:
            meta = parsed_members.get(member_id, {})
            member_type: str = meta.get("member_type", "beam")
            override = overrides.get(member_id, {})

            # Add member structural self-weight, differentiated by slab system,
            # on top of the superimposed dead load (finishes/screed/services/etc.).
            self_weight = _member_self_weight_kNm2(meta)
            effective_gk = (
                gk_base + self_weight + float(override.get("dead_extra_kNm2", 0.0))
            )
            effective_qk = float(override.get("imposed_override_kNm2") or qk_base)

            uls_udl = LoadCombinationEngine.factor_loads(
                effective_gk + cladding_gk, effective_qk, 0.0,
                design_code, LimitState.ULS_DOMINANT,
            )
            sls_udl = LoadCombinationEngine.factor_loads(
                effective_gk + cladding_gk, effective_qk, 0.0,
                design_code, LimitState.SLS_CHARACTERISTIC,
            )

            raw_spans: list[dict] = meta.get("spans", [{"span_id": "S1", "length_m": 5.0}])
            spans_data = [
                {
                    "span_id": s.get("span_id", f"S{i + 1}"),
                    "length_m": float(s.get("length_m", 5.0)),
                    "loads": {
                        "udl_gk": round(effective_gk, 3),
                        "udl_qk": round(effective_qk, 3),
                        "n_uls": round(uls_udl, 3),
                        "n_sls": round(sls_udl, 3),
                        "point_loads": s.get("point_loads", []),
                    },
                    "pattern_loading_flag": len(raw_spans) >= 3,
                }
                for i, s in enumerate(raw_spans)
            ]

            serialized = LoadSerializer.serialize_member(
                member_id=member_id,
                member_type=member_type,
                design_code=design_code,
                spans_data=spans_data,
                combination_used=combo_label,
                notes=override.get("notes", ""),
            )
            members_output.append(serialized)

        return {
            "design_code": design_code_str,
            "members": members_output,
            "combination_used": combo_label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
loading_service = LoadingService()
