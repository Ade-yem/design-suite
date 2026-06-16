"""
services/analysis.py
====================
Analysis service — orchestrates the structural analysis engine.

Both the FastAPI analysis router and the Analyst Agent call this service
directly; neither runs engineering calculations itself.

Public API
----------
analysis_service.run(project_id, member_ids, options)   → dict
analysis_service.get_results(project_id)                → dict
analysis_service.get_member_result(project_id, mid)     → dict
analysis_service.clear(project_id)                      → None
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from schemas.project import ProjectStatus
from storage.project_store import project_store

logger = logging.getLogger(__name__)


# ── In-memory result store ────────────────────────────────────────────────────

class _AnalysisStore:
    """
    In-memory store for analysis results.
    Delegates internally to stage_result_store.
    """

    def __init__(self) -> None:
        pass

    def set(self, project_id: str, data: dict) -> None:
        """Store analysis results for a project."""
        from storage.stage_result_store import stage_result_store
        stage_result_store._memory_store[(project_id, "analysis")] = data

    def get(self, project_id: str) -> Optional[dict]:
        """Return analysis results or None."""
        from storage.stage_result_store import stage_result_store
        return stage_result_store._memory_store.get((project_id, "analysis"))

    def clear(self, project_id: str) -> None:
        """Remove results for a project."""
        from storage.stage_result_store import stage_result_store
        stage_result_store._memory_store.pop((project_id, "analysis"), None)


_store = _AnalysisStore()


# ── Service class ─────────────────────────────────────────────────────────────

class AnalysisService:
    """
    Structural analysis orchestration service.

    Wraps ``core.analysis.AnalysisEngine`` and ``_AnalysisStore``.
    Agents call ``await analysis_service.run(...)`` directly — no HTTP, no polling.
    Routers schedule the same call as a background task for progress tracking.
    """

    async def run(
        self,
        project_id: str,
        member_ids: Optional[list[str]] = None,
        options: Optional[dict] = None,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> dict:
        """
        Run the structural analysis engine for a project.

        Runs the CPU-bound ``AnalysisEngine`` in a thread pool so the event loop
        is not blocked.  Advances the project to ``ANALYSIS_COMPLETE`` when done.

        Parameters
        ----------
        project_id : str
            Target project.
        member_ids : list[str] | None
            Specific members to analyse.  ``None`` → all registered members.
        options : dict | None
            Analysis configuration:
            ``{pattern_loading, self_weight_iteration, max_iterations}``.
        progress_cb : Callable[[str, float], None] | None
            Optional callback invoked with ``(current_step, progress_pct)`` during
            analysis.  Used by the router to push updates to the ``job_store``.

        Returns
        -------
        dict
            Analysis results in ``AnalysisResultsResponse`` shape:
            ``{analysis_id, design_code, member_count, members, generated_at}``

        Raises
        ------
        ValueError
            If no load output is available for this project.
        """
        opts = options or {}
        all_ids = member_ids or await project_store.get_member_ids(project_id)

        # Validate prerequisites
        from services.loading import loading_service
        try:
            load_output = loading_service.get_output(project_id)
        except KeyError as exc:
            raise ValueError(
                f"Cannot run analysis for project '{project_id}': "
                "run load combinations first."
            ) from exc

        from services.files import file_service
        parsed: dict | None = None
        try:
            parsed = await file_service.get_parsed(project_id)
            parsed_members: dict[str, dict] = {
                m["member_id"]: m for m in parsed.get("members", [])
            }
        except KeyError:
            parsed_members = {}

        # Stamp the building storey height onto staircase members so the flight
        # geometry (riser count, span) is derived from it rather than defaults.
        try:
            proj = await project_store.get(project_id, bypass_tenant_check=True)
            storey_h = getattr(proj, "storey_height_m", None) if proj else None
            if storey_h:
                for m in parsed_members.values():
                    if str(m.get("member_type", "")).lower() == "staircase":
                        m.setdefault("meta", {})["storey_height_m"] = storey_h
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Could not stamp storey height on staircases: %s", exc)

        # Prepare member data list for the engine
        load_members: dict[str, dict] = {
            m["member_id"]: m for m in load_output.get("members", [])
        }

        total = max(len(all_ids), 1)
        results: list[dict] = []

        def _run_analysis_sync() -> list[dict]:
            """Synchronous two-pass analysis loop — runs in a thread pool."""
            from core.analysis.engine import AnalysisEngine
            from core.loading.takedown import VerticalLoadTakedownEngine
            from models.loading.schema import MemberLoadOutput

            design_code = load_output.get("design_code", "BS8110")
            engine = AnalysisEngine(design_code=design_code)

            HORIZONTAL = {"beam", "slab", "staircase"}
            VERTICAL   = {"column", "wall", "footing"}

            # ── Pass 1: horizontal members ────────────────────────────────
            horizontal_results: dict[str, dict] = {}
            h_ids = [m for m in all_ids if load_members.get(m, {}).get("member_type", "").lower() in HORIZONTAL]
            other_ids = [m for m in all_ids if m not in h_ids]

            for i, mid in enumerate(h_ids, start=1):
                pct = (i / max(len(h_ids), 1)) * 40  # 0-40%
                if progress_cb:
                    progress_cb(f"Pass 1 — {mid} ({i}/{len(h_ids)})…", pct)

                load_member_data = load_members.get(mid)
                geometry_meta = parsed_members.get(mid, {}).get("meta", {})

                if load_member_data is None:
                    horizontal_results[mid] = {"member_id": mid, "status": "skipped", "reason": "No load data"}
                    continue
                try:
                    load_obj = MemberLoadOutput(**load_member_data)
                    result = engine.analyze_member(load_obj, geometry_meta)
                    horizontal_results[mid] = result.model_dump()
                except Exception as exc:
                    logger.warning("Analysis failed for member %s: %s", mid, exc)
                    horizontal_results[mid] = {"member_id": mid, "status": "error", "reason": str(exc)}

            # ── Takedown ──────────────────────────────────────────────────
            if progress_cb:
                progress_cb("Running vertical load takedown…", 45)
            try:
                members_list = list(parsed_members.values())
                project_params = opts.get("project_params", {})
                col_axial, footing_members, footing_loads = (
                    VerticalLoadTakedownEngine.compute_column_axial_loads(
                        members=members_list,
                        beam_analysis_results=horizontal_results,
                        beam_loading_data=load_members,
                        project_params=project_params,
                        design_code=design_code,
                    )
                )
                # Patch column meta with real N_uls
                for col_id, axial in col_axial.items():
                    if col_id in parsed_members:
                        parsed_members[col_id]["meta"]["N_uls"] = axial["N_uls"]
                        parsed_members[col_id]["meta"]["_takedown"] = axial

                # Inject auto-generated footing members
                for fm in footing_members:
                    fid = fm["member_id"]
                    parsed_members[fid] = fm
                for fl in footing_loads:
                    fid = fl["member_id"]
                    load_members[fid] = fl
                    if fid not in all_ids:
                        all_ids.append(fid)
            except Exception as exc:
                logger.warning("Takedown failed — columns will use placeholder N_uls: %s", exc)

            # ── Pass 2: vertical members + injected footings ───────────────
            v_ids = [m for m in all_ids if load_members.get(m, {}).get("member_type", "").lower() in VERTICAL]
            remaining_ids = [m for m in all_ids if m not in h_ids and m not in v_ids]

            vertical_results: list[dict] = []
            for i, mid in enumerate(v_ids, start=1):
                pct = 50 + (i / max(len(v_ids), 1)) * 40  # 50-90%
                if progress_cb:
                    progress_cb(f"Pass 2 — {mid} ({i}/{len(v_ids)})…", pct)

                load_member_data = load_members.get(mid)
                geometry_meta = parsed_members.get(mid, {}).get("meta", {})

                if load_member_data is None:
                    vertical_results.append({"member_id": mid, "status": "skipped", "reason": "No load data"})
                    continue
                try:
                    load_obj = MemberLoadOutput(**load_member_data)
                    result = engine.analyze_member(load_obj, geometry_meta)
                    vertical_results.append(result.model_dump())
                except Exception as exc:
                    logger.warning("Analysis failed for member %s: %s", mid, exc)
                    vertical_results.append({"member_id": mid, "status": "error", "reason": str(exc)})

            # Members with no load data in either pass
            skipped: list[dict] = []
            for mid in remaining_ids:
                if progress_cb:
                    progress_cb(f"Skipping {mid}…", 92)
                load_member_data = load_members.get(mid)
                if load_member_data is None:
                    skipped.append({"member_id": mid, "status": "skipped", "reason": "No load data"})
                    continue
                try:
                    geometry_meta = parsed_members.get(mid, {}).get("meta", {})
                    load_obj = MemberLoadOutput(**load_member_data)
                    result = engine.analyze_member(load_obj, geometry_meta)
                    skipped.append(result.model_dump())
                except Exception as exc:
                    skipped.append({"member_id": mid, "status": "error", "reason": str(exc)})

            return list(horizontal_results.values()) + vertical_results + skipped

        results = await asyncio.to_thread(_run_analysis_sync)

        # Persist auto-generated footings back into the canvas-readable geometry.
        # The takedown synthesises one footing per base column but previously only
        # injected them into this in-memory working set, so the app's own
        # foundations were invisible. Footings are additive, derived members —
        # column N_uls patches already landed on the shared member objects, so we
        # only append the new footings and re-register.
        try:
            if parsed is not None:
                existing_ids = {m.get("member_id") for m in parsed.get("members", [])}
                new_footings = [
                    m
                    for mid, m in parsed_members.items()
                    if m.get("member_type") == "footing" and mid not in existing_ids
                ]
                if new_footings:
                    parsed["members"] = list(parsed.get("members", [])) + new_footings
                    await file_service.register_geometry(project_id, parsed)
                    await project_store.register_members_batch(
                        project_id, [m["member_id"] for m in new_footings]
                    )
        except Exception as exc:  # pragma: no cover - best-effort visibility
            logger.warning("Could not persist auto-generated footings: %s", exc)

        design_code = load_output.get("design_code", "BS8110")
        output = {
            "analysis_id": f"ANA-{project_id[-8:].upper()}",
            "design_code": design_code,
            "member_count": len(results),
            "members": results,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        _store.set(project_id, output)
        await project_store.advance_status(project_id, ProjectStatus.ANALYSIS_COMPLETE)
        await self._db_save_analysis(project_id, output)

        logger.info(
            "Analysis complete for project %s: %d member(s).",
            project_id,
            len(results),
        )
        return output

    def get_results(self, project_id: str) -> dict:
        """
        Return cached analysis results.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict

        Raises
        ------
        KeyError
            If analysis has not been run yet.
        """
        data = _store.get(project_id)
        if data is None:
            raise KeyError(
                f"No analysis results for project '{project_id}'. "
                "Run analysis first."
            )
        return data

    def get_member_result(self, project_id: str, member_id: str) -> dict:
        """
        Return the analysis result for a single member.

        Parameters
        ----------
        project_id : str
        member_id : str

        Returns
        -------
        dict

        Raises
        ------
        KeyError
            If no result exists for this member.
        """
        results = self.get_results(project_id)
        member = next(
            (m for m in results.get("members", []) if m.get("member_id") == member_id),
            None,
        )
        if member is None:
            raise KeyError(f"Member '{member_id}' not found in analysis results.")
        return member

    def merge_results(self, project_id: str, new_results: list[dict]) -> dict:
        """
        Merge updated member results into the cached output (re-analysis loop).

        Used by the Analyst Agent when the Designer triggers a self-weight
        convergence loop for specific members.

        Parameters
        ----------
        project_id : str
        new_results : list[dict]
            Updated member result dicts.

        Returns
        -------
        dict
            The merged result set.
        """
        existing = _store.get(project_id) or {"members": []}
        existing_map = {m["member_id"]: m for m in existing.get("members", [])}
        for m in new_results:
            existing_map[m["member_id"]] = m
        merged = {**existing, "members": list(existing_map.values())}
        _store.set(project_id, merged)
        return merged

    async def clear(self, project_id: str) -> None:
        """
        Clear analysis results for a project.

        Parameters
        ----------
        project_id : str
        """
        _store.clear(project_id)
        from storage.stage_result_store import stage_result_store
        await stage_result_store.clear(project_id, "analysis")

    # ── DB persistence helpers ────────────────────────────────────────────────

    async def ensure_cached(self, project_id: str) -> None:
        """Load analysis results from DB into cache if missing."""
        from storage.stage_result_store import stage_result_store
        payload = await stage_result_store.get(project_id, "analysis")
        if payload:
            _store.set(project_id, payload)

    async def _db_save_analysis(self, project_id: str, output: dict) -> None:
        """Upsert analysis output. Silent no-op if DB unavailable."""
        from storage.stage_result_store import stage_result_store
        await stage_result_store.save(project_id, "analysis", output)


# ── Singleton ─────────────────────────────────────────────────────────────────
analysis_service = AnalysisService()
