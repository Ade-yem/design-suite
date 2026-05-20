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

    Attributes
    ----------
    _results : dict[str, dict]
        Analysis output per project (full ``AnalysisOutputSchema`` dict).
    """

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    def set(self, project_id: str, data: dict) -> None:
        """Store analysis results for a project."""
        self._results[project_id] = data

    def get(self, project_id: str) -> Optional[dict]:
        """Return analysis results or None."""
        return self._results.get(project_id)

    def clear(self, project_id: str) -> None:
        """Remove results for a project."""
        self._results.pop(project_id, None)


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
        try:
            parsed = file_service.get_parsed(project_id)
            parsed_members: dict[str, dict] = {
                m["member_id"]: m for m in parsed.get("members", [])
            }
        except KeyError:
            parsed_members = {}

        # Prepare member data list for the engine
        load_members: dict[str, dict] = {
            m["member_id"]: m for m in load_output.get("members", [])
        }

        total = max(len(all_ids), 1)
        results: list[dict] = []

        def _run_analysis_sync() -> list[dict]:
            """Synchronous analysis loop — runs in a thread pool."""
            from core.analysis.engine import AnalysisEngine
            from models.loading.schema import MemberLoadOutput

            design_code = load_output.get("design_code", "BS8110")
            engine = AnalysisEngine(design_code=design_code)

            member_results = []
            for i, mid in enumerate(all_ids, start=1):
                pct = (i / total) * 100
                step = f"Analysing member {mid} ({i}/{total})…"
                if progress_cb:
                    progress_cb(step, pct)

                load_member_data = load_members.get(mid)
                geometry_meta = parsed_members.get(mid, {}).get("meta", {})

                if load_member_data is None:
                    logger.warning("No load data for member %s — skipping.", mid)
                    member_results.append({
                        "member_id": mid,
                        "status": "skipped",
                        "reason": "No load data available",
                    })
                    continue

                try:
                    load_obj = MemberLoadOutput(**load_member_data)
                    result = engine.analyze_member(load_obj, geometry_meta)
                    member_results.append(result.model_dump())
                except Exception as exc:
                    logger.warning("Analysis failed for member %s: %s", mid, exc)
                    member_results.append({
                        "member_id": mid,
                        "status": "error",
                        "reason": str(exc),
                    })

            return member_results

        results = await asyncio.to_thread(_run_analysis_sync)

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

    def clear(self, project_id: str) -> None:
        """
        Clear analysis results for a project.

        Parameters
        ----------
        project_id : str
        """
        _store.clear(project_id)

    # ── DB persistence helper ─────────────────────────────────────────────────

    async def _db_save_analysis(self, project_id: str, output: dict) -> None:
        """Upsert analysis output to ProjectAnalysis. Silent no-op if DB unavailable."""
        from config import settings
        if settings.PROJECT_STORE_BACKEND != "postgres":
            return
        try:
            from db.session import get_session_maker
            from db.models.pipeline import ProjectAnalysis
            from sqlalchemy import select

            session_maker = get_session_maker()
            async with session_maker() as session:
                row = (await session.execute(
                    select(ProjectAnalysis).where(ProjectAnalysis.project_id == project_id)
                )).scalar_one_or_none()

                out_str = json.dumps(output)
                analysis_id = output.get("analysis_id", "")
                design_code = output.get("design_code", "BS8110")

                if row:
                    row.output = out_str
                    row.analysis_id = analysis_id
                    row.design_code = design_code
                else:
                    session.add(ProjectAnalysis(
                        project_id=project_id,
                        analysis_id=analysis_id,
                        design_code=design_code,
                        output=out_str,
                    ))
                await session.commit()
        except RuntimeError:
            pass  # DATABASE_URL not configured
        except Exception as exc:
            logger.warning("DB analysis save failed for project %s: %s", project_id, exc)


# ── Singleton ─────────────────────────────────────────────────────────────────
analysis_service = AnalysisService()
