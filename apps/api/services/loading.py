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

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from schemas.loading import LoadValidationResult
from schemas.project import ProjectStatus
from storage.project_store import project_store

logger = logging.getLogger(__name__)


# ── In-memory stores ──────────────────────────────────────────────────────────

class _LoadingStore:
    """
    In-memory store for load definitions and combination output.

    Attributes
    ----------
    _definitions : dict[str, dict]
        Raw load definition per project.
    _output : dict[str, dict]
        Factored load output (from combination engine) per project.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, dict[str, Any]] = {}
        self._output: dict[str, dict[str, Any]] = {}

    def set_definition(self, project_id: str, data: dict) -> None:
        """Store load definition for a project."""
        self._definitions[project_id] = data

    def get_definition(self, project_id: str) -> Optional[dict]:
        """Return load definition or None."""
        return self._definitions.get(project_id)

    def set_output(self, project_id: str, data: dict) -> None:
        """Store combination output for a project."""
        self._output[project_id] = data

    def get_output(self, project_id: str) -> Optional[dict]:
        """Return combination output or None."""
        return self._output.get(project_id)

    def clear(self, project_id: str) -> None:
        """Remove all loading data for a project."""
        self._definitions.pop(project_id, None)
        self._output.pop(project_id, None)


_store = _LoadingStore()


# ── Service class ─────────────────────────────────────────────────────────────

class LoadingService:
    """
    Load definition and combination service.

    Wraps the ``core.loading`` combination engine and the loading store.
    Agents and routers call this service — they never perform load arithmetic
    themselves.
    """

    def define(self, project_id: str, definition: dict) -> dict:
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
        self._schedule_db_save(self._db_save_loads(project_id, definition, None))
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

    def run_combinations(self, project_id: str) -> dict:
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
        definition = _store.get_definition(project_id)
        if not definition:
            raise ValueError(
                f"No load definition for project '{project_id}'. "
                "Submit a load definition first."
            )

        output = self._run_engine(project_id, definition)
        _store.set_output(project_id, output)
        project_store.advance_status(project_id, ProjectStatus.LOADING_DEFINED)
        self._schedule_db_save(self._db_save_loads(project_id, definition, output))

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

    def update_member_loads(
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

    async def _db_save_loads(self, project_id: str, definition: dict, output: dict | None) -> None:
        """Upsert load definition and output to ProjectLoad. Silent no-op if DB unavailable."""
        from config import settings
        if settings.PROJECT_STORE_BACKEND != "postgres":
            return
        try:
            from db.session import get_session_maker
            from db.models.project import ProjectLoad
            from sqlalchemy import select

            session_maker = get_session_maker()
            async with session_maker() as session:
                row = (await session.execute(
                    select(ProjectLoad).where(ProjectLoad.project_id == project_id)
                )).scalar_one_or_none()

                def_str = json.dumps(definition)
                out_str = json.dumps(output) if output is not None else None

                if row:
                    row.definition = def_str
                    if out_str is not None:
                        row.output = out_str
                else:
                    session.add(ProjectLoad(
                        project_id=project_id,
                        definition=def_str,
                        output=out_str,
                    ))
                await session.commit()
        except RuntimeError:
            pass  # DATABASE_URL not configured
        except Exception as exc:
            logger.warning("DB load save failed for project %s: %s", project_id, exc)

    def _schedule_db_save(self, coro) -> None:
        """Schedule a DB-write coroutine on the running event loop (fire-and-forget)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(coro)
        except RuntimeError:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_engine(self, project_id: str, definition: dict) -> dict:
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
            parsed = file_service.get_parsed(project_id)
            parsed_members: dict[str, dict] = {
                m["member_id"]: m for m in parsed.get("members", [])
            }
        except KeyError:
            parsed_members = {}

        member_ids = project_store.get_member_ids(project_id)
        effective_ids = member_ids or list(parsed_members.keys())

        members_output: list[dict] = []
        for member_id in effective_ids:
            meta = parsed_members.get(member_id, {})
            member_type: str = meta.get("member_type", "beam")
            override = overrides.get(member_id, {})

            effective_gk = gk_base + float(override.get("dead_extra_kNm2", 0.0))
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
