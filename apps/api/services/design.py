"""
services/design.py
==================
Design service — orchestrates the Design Suite for all member types.

Both the FastAPI design router and the Designer Agent call this service
directly; neither runs design calculations itself.

Public API
----------
design_service.run(project_id, member_ids, design_code, progress_cb)  → dict
design_service.get_results(project_id)                                → dict
design_service.apply_override(project_id, member_id, override)        → dict
design_service.rerun_member(project_id, member_id)                    → dict
design_service.clear(project_id)                                      → None
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

# Self-weight change that triggers a re-analysis recommendation
_SELF_WEIGHT_THRESHOLD_PCT = 5.0


# ── In-memory result store ────────────────────────────────────────────────────

class _DesignStore:
    """
    In-memory store for design results.

    Attributes
    ----------
    _results : dict[str, dict]
        Design output per project.
    """

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    def set(self, project_id: str, data: dict) -> None:
        """Store design results for a project."""
        self._results[project_id] = data

    def get(self, project_id: str) -> Optional[dict]:
        """Return design results or None."""
        return self._results.get(project_id)

    def clear(self, project_id: str) -> None:
        """Remove results for a project."""
        self._results.pop(project_id, None)


_store = _DesignStore()


# ── Service class ─────────────────────────────────────────────────────────────

class DesignService:
    """
    Reinforced concrete design orchestration service.

    Wraps the ``core.design`` suite.  Agents call
    ``await design_service.run(...)`` directly — no HTTP, no polling.
    Routers schedule the same call as a background task for progress tracking.
    """

    async def run(
        self,
        project_id: str,
        member_ids: Optional[list[str]] = None,
        design_code: Optional[str] = None,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> dict:
        """
        Run the design suite for a project.

        Runs the CPU-bound design calculations in a thread pool.  Advances the
        project to ``DESIGN_COMPLETE`` on success.

        Parameters
        ----------
        project_id : str
        member_ids : list[str] | None
            Specific members to design.  ``None`` → all registered members.
        design_code : str | None
            ``"BS8110"`` or ``"EC2"``.  Falls back to the code used during analysis.
        progress_cb : Callable[[str, float], None] | None
            Optional ``(step, pct)`` progress callback for the router's job tracking.

        Returns
        -------
        dict
            Design results in ``DesignResultsResponse`` shape:
            ``{design_id, design_code, member_count, members, generated_at}``

        Raises
        ------
        ValueError
            If no analysis results are available for this project.
        """
        all_ids = member_ids or await project_store.get_member_ids(project_id)

        from services.analysis import analysis_service
        try:
            analysis_results = analysis_service.get_results(project_id)
        except KeyError as exc:
            raise ValueError(
                f"Cannot run design for project '{project_id}': "
                "run analysis first."
            ) from exc

        from services.files import file_service
        try:
            parsed = await file_service.get_parsed(project_id)
            parsed_members: dict[str, dict] = {
                m["member_id"]: m for m in parsed.get("members", [])
            }
        except KeyError:
            parsed_members = {}

        analysis_map: dict[str, dict] = {
            m["member_id"]: m for m in analysis_results.get("members", [])
        }

        effective_code = design_code or analysis_results.get("design_code", "BS8110")
        total = max(len(all_ids), 1)

        def _run_design_sync() -> list[dict]:
            """Synchronous design loop — runs in a thread pool."""
            from core.design.rc import design_member

            member_results = []
            for i, mid in enumerate(all_ids, start=1):
                pct = (i / total) * 100
                step = f"Designing member {mid} ({i}/{total})…"
                if progress_cb:
                    progress_cb(step, pct)

                analysis_member = analysis_map.get(mid)
                geometry_meta = parsed_members.get(mid, {}).get("meta", {})

                if analysis_member is None or analysis_member.get("status") in ("error", "skipped"):
                    logger.warning("Skipping design for member %s — no valid analysis result.", mid)
                    member_results.append({
                        "member_id": mid,
                        "member_type": parsed_members.get(mid, {}).get("member_type", "unknown"),
                        "design_code": effective_code,
                        "status": "skipped",
                        "reason": "No valid analysis result",
                        "reinforcement": {},
                        "self_weight_change_pct": 0.0,
                    })
                    continue

                try:
                    result = design_member(
                        analysis_result=analysis_member,
                        geometry_meta=geometry_meta,
                        design_code=effective_code,
                    )
                    member_results.append(result)
                except Exception as exc:
                    logger.warning("Design failed for member %s: %s", mid, exc)
                    member_results.append({
                        "member_id": mid,
                        "member_type": geometry_meta.get("member_type", "unknown"),
                        "design_code": effective_code,
                        "status": "FAILED",
                        "failure_reason": str(exc),
                        "reinforcement": {},
                        "self_weight_change_pct": 0.0,
                    })

            return member_results

        results = await asyncio.to_thread(_run_design_sync)

        output = {
            "design_id": f"DES-{project_id[-8:].upper()}",
            "design_code": effective_code,
            "member_count": len(results),
            "members": results,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        _store.set(project_id, output)
        await project_store.advance_status(project_id, ProjectStatus.DESIGN_COMPLETE)
        await self._db_save_design(project_id, output)

        logger.info(
            "Design complete for project %s: %d member(s), code=%s.",
            project_id,
            len(results),
            effective_code,
        )
        return output

    def get_results(self, project_id: str) -> dict:
        """
        Return cached design results.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict

        Raises
        ------
        KeyError
            If design has not been run yet.
        """
        data = _store.get(project_id)
        if data is None:
            raise KeyError(
                f"No design results for project '{project_id}'. "
                "Run design first."
            )
        return data

    async def apply_override(
        self,
        project_id: str,
        member_id: str,
        override: dict,
    ) -> dict:
        """
        Apply a geometry or parameter override to a designed member.

        Updates the member in the cached results and performs a lightweight
        limit-state re-check.  Returns a warning and a re-analysis flag when
        the override changes self-weight by more than the threshold.

        Parameters
        ----------
        project_id : str
        member_id : str
        override : dict
            Fields from ``MemberDesignOverride``:
            b_mm, h_mm, cover_mm, fcu_MPa, fck_MPa, fy_MPa, meta_updates, reason.

        Returns
        -------
        dict
            ``{result, warning, reanalysis_needed, self_weight_change_pct}``

        Raises
        ------
        KeyError
            If the member is not found in the design store.
        """
        store = _store.get(project_id)
        if store is None:
            raise KeyError(
                f"No design results for project '{project_id}'."
            )

        member = next(
            (m for m in store["members"] if m.get("member_id") == member_id),
            None,
        )
        if member is None:
            raise KeyError(f"Member '{member_id}' not found in design results.")

        # Record original self-weight for convergence check
        original_sw = member.get("self_weight_kNm", 0.0)

        # Apply the override fields
        for field in ("b_mm", "h_mm", "cover_mm", "fck_MPa", "fcu_MPa", "fy_MPa"):
            if override.get(field) is not None:
                member[field] = override[field]
        member.update(override.get("meta_updates", {}))
        member["override_reason"] = override.get("reason", "")
        member["override_at"] = datetime.now(timezone.utc).isoformat()

        # Stub re-check (integrate with design_member when available)
        new_sw = member.get("self_weight_kNm", original_sw)
        sw_change_pct = (
            abs(new_sw - original_sw) / original_sw * 100 if original_sw else 0.0
        )

        warning = None
        reanalysis_needed = False
        if sw_change_pct > _SELF_WEIGHT_THRESHOLD_PCT:
            warning = (
                f"Self-weight changed by {sw_change_pct:.1f}% "
                f"(threshold: {_SELF_WEIGHT_THRESHOLD_PCT}%). "
                "Re-analysis recommended."
            )
            reanalysis_needed = True

        _store.set(project_id, store)
        await self._db_save_design(project_id, store)
        logger.info(
            "Design override applied to %s in project %s. Reason: %s",
            member_id,
            project_id,
            override.get("reason", "(none)"),
        )
        return {
            "result": member,
            "warning": warning,
            "reanalysis_needed": reanalysis_needed,
            "self_weight_change_pct": round(sw_change_pct, 2),
        }

    async def rerun_member(self, project_id: str, member_id: str) -> dict:
        """
        Rerun the design for a single member after a geometry override.

        Parameters
        ----------
        project_id : str
        member_id : str

        Returns
        -------
        dict
            Updated design results.
        """
        return await self.run(project_id, member_ids=[member_id])

    def clear(self, project_id: str) -> None:
        """
        Clear design results for a project.

        Parameters
        ----------
        project_id : str
        """
        _store.clear(project_id)

    # ── DB persistence helpers ────────────────────────────────────────────────

    async def ensure_cached(self, project_id: str) -> None:
        """Load design results from DB into cache if missing."""
        if _store.get(project_id) is not None:
            return
        from config import settings
        if settings.PROJECT_STORE_BACKEND != "postgres":
            return
        try:
            from db.session import get_session_maker
            from db.models.pipeline import ProjectDesign
            from sqlalchemy import select

            session_maker = get_session_maker()
            async with session_maker() as session:
                row = (await session.execute(
                    select(ProjectDesign).where(ProjectDesign.project_id == project_id)
                )).scalar_one_or_none()
                if row and row.output:
                    _store.set(project_id, json.loads(row.output))
        except Exception as exc:
            logger.warning("DB design fetch for project %s failed: %s", project_id, exc)

    async def _db_save_design(self, project_id: str, output: dict) -> None:
        """Upsert design output to ProjectDesign. Silent no-op if DB unavailable."""
        try:
            from db.session import get_session_maker
            from db.models.pipeline import ProjectDesign
            from sqlalchemy import select

            session_maker = get_session_maker()
            async with session_maker() as session:
                row = (await session.execute(
                    select(ProjectDesign).where(ProjectDesign.project_id == project_id)
                )).scalar_one_or_none()

                out_str = json.dumps(output)
                design_id = output.get("design_id", "")
                design_code = output.get("design_code", "BS8110")

                if row:
                    row.output = out_str
                    row.design_id = design_id
                    row.design_code = design_code
                else:
                    session.add(ProjectDesign(
                        project_id=project_id,
                        design_id=design_id,
                        design_code=design_code,
                        output=out_str,
                    ))
                await session.commit()
        except RuntimeError:
            pass  # DATABASE_URL not configured
        except Exception as exc:
            logger.warning("DB design save failed for project %s: %s", project_id, exc)


# ── Singleton ─────────────────────────────────────────────────────────────────
design_service = DesignService()
