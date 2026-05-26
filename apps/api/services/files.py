"""
services/files.py
=================
File service — owns all geometry and scale data for a project.

This module is the single source of truth for parsed DXF/PDF data.
Both the FastAPI files router and the Vision Agent (parser_node) call
this service directly; neither holds its own geometry store.

Public API
----------
file_service.parse(project_id, file_path)        → dict  (Structural JSON)
file_service.get_parsed(project_id)              → dict
file_service.get_scale(project_id)               → dict
file_service.confirm_scale(project_id, ...)      → dict
file_service.verify_geometry(project_id, ...)    → dict
file_service.register_geometry(project_id, data) → None  (for manual/test injection)
file_service.clear(project_id)                   → None
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.parsing import parse_file
from storage.project_store import project_store
from schemas.project import ProjectStatus

logger = logging.getLogger(__name__)


class _GeometryStore:
    """
    Thread-safe in-memory store for parsed geometry and scale data.

    Keyed by ``project_id``.  Replace with a database-backed store when
    ``PROJECT_STORE_BACKEND=postgres`` is active (migrate
    ``_parsed`` → ``ProjectGeometry`` table).

    Attributes
    ----------
    _parsed : dict[str, dict]
        Parsed structural JSON per project.
    _scale : dict[str, dict]
        Scale / unit info per project.
    """

    def __init__(self) -> None:
        self._parsed: dict[str, dict[str, Any]] = {}
        self._scale: dict[str, dict[str, Any]] = {}

    def set_parsed(self, project_id: str, data: dict) -> None:
        """
        Store parsed structural JSON for a project.

        Parameters
        ----------
        project_id : str
        data : dict
            Structural JSON schema output from the parser.
        """
        self._parsed[project_id] = data

    def get_parsed(self, project_id: str) -> Optional[dict]:
        """
        Retrieve parsed structural JSON.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict | None
        """
        return self._parsed.get(project_id)

    def set_scale(self, project_id: str, scale: dict) -> None:
        """
        Store scale / unit information.

        Parameters
        ----------
        project_id : str
        scale : dict
            ``{factor, unit, detected, confirmed}``
        """
        self._scale[project_id] = scale

    def get_scale(self, project_id: str) -> Optional[dict]:
        """
        Retrieve scale info.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict | None
        """
        return self._scale.get(project_id)

    def clear(self, project_id: str) -> None:
        """
        Remove all geometry and scale data for a project.

        Parameters
        ----------
        project_id : str
        """
        self._parsed.pop(project_id, None)
        self._scale.pop(project_id, None)


_store = _GeometryStore()


class FileService:
    """
    File parsing and geometry management service.

    Wraps ``core.parsing`` and ``_GeometryStore``.  Agents and routers call
    this service — they never touch the store or the parser directly.
    """

    async def parse(self, project_id: str, file_path: str) -> dict:
        """
        Parse a DXF or PDF file and cache the resulting structural JSON.

        Runs the CPU-bound parser in a thread pool so the event loop is not
        blocked.  On completion, advances the project to ``FILE_UPLOADED``
        and populates the geometry store.

        Parameters
        ----------
        project_id : str
            Owning project.
        file_path : str
            Absolute path to the uploaded DXF or PDF file.

        Returns
        -------
        dict
            Structural JSON:
            ``{members, scale, raw_entity_count, parse_warnings, file_path, parsed_at}``

        Raises
        ------
        RuntimeError
            If ``ezdxf`` (DXF) or ``pymupdf`` (PDF) is missing.
        OSError
            If the file cannot be read.
        """
        logger.info("Parsing file '%s' for project %s.", file_path, project_id)

        # Run synchronous parser off the event loop
        parsed: dict = await asyncio.to_thread(parse_file, file_path)

        # Normalize the scale dictionary between DXF and PDF schemas
        scale_dict = parsed.get("scale")
        if not scale_dict and "metadata" in parsed:
            meta = parsed["metadata"]
            scale_dict = {
                "factor": meta.get("conversion_factor", 1.0),
                "unit": meta.get("units_label", "mm"),
                "detected": True,
                "confirmed": False
            }
            parsed["scale"] = scale_dict
            
        if not scale_dict:
            scale_dict = {
                "factor": 1.0,
                "unit": "mm",
                "detected": False,
                "confirmed": False
            }
            parsed["scale"] = scale_dict

        _store.set_parsed(project_id, parsed)
        _store.set_scale(project_id, scale_dict)
        self._schedule_db_save(self._db_save_geometry(project_id, parsed, scale_dict))

        # Batch register all detected members with the project store
        mids = [member.get("member_id") for member in parsed.get("members", []) if member.get("member_id")]
        await project_store.register_members_batch(project_id, mids)

        # Advance pipeline status
        await project_store.advance_status(project_id, ProjectStatus.FILE_UPLOADED)

        logger.info(
            "Parse complete for project %s: %d member(s) detected.",
            project_id,
            len(parsed.get("members", [])),
        )
        return parsed

    def get_parsed(self, project_id: str) -> dict:
        """
        Return the cached structural JSON for a project.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict
            Cached structural JSON.

        Raises
        ------
        KeyError
            If no parsed data exists for this project.
        """
        data = _store.get_parsed(project_id)
        if data is None:
            raise KeyError(
                f"No parsed geometry for project '{project_id}'. "
                "Parse a file first via file_service.parse()."
            )
        return data

    def get_scale(self, project_id: str) -> dict:
        """
        Return the scale / unit info detected during parsing.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        dict
            ``{factor, unit, detected, confirmed}``

        Raises
        ------
        KeyError
            If no scale data exists for this project.
        """
        scale = _store.get_scale(project_id)
        if scale is None:
            raise KeyError(
                f"No scale data for project '{project_id}'. "
                "Parse a file first via file_service.parse()."
            )
        return scale

    def confirm_scale(
        self,
        project_id: str,
        scale_factor: float,
        unit_label: str,
    ) -> dict:
        """
        Store a user-confirmed scale factor, overriding the auto-detected value.

        Updates spans_m in the cached geometry to reflect the corrected scale.

        Parameters
        ----------
        project_id : str
        scale_factor : float
            Numeric multiplier (e.g. 0.001 to convert mm DXF units to metres).
        unit_label : str
            Human-readable unit string (``"mm"`` or ``"m"``).

        Returns
        -------
        dict
            Updated scale record.
        """
        existing = _store.get_scale(project_id) or {}
        old_factor = existing.get("factor", scale_factor)

        new_scale = {
            "factor": scale_factor,
            "unit": unit_label,
            "detected": False,
            "confirmed": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _store.set_scale(project_id, new_scale)
        parsed_after = _store.get_parsed(project_id) or {}
        self._schedule_db_save(self._db_save_geometry(project_id, parsed_after, new_scale))

        # Rescale spans_m in cached geometry
        parsed = _store.get_parsed(project_id)
        if parsed and old_factor and old_factor != scale_factor:
            ratio = scale_factor / old_factor
            for member in parsed.get("members", []):
                member["spans_m"] = [round(s * ratio, 3) for s in member.get("spans_m", [])]
                for span in member.get("spans", []):
                    span["length_m"] = round(span["length_m"] * ratio, 3)
            _store.set_parsed(project_id, parsed)

        logger.info(
            "Scale confirmed for project %s: factor=%.6f unit=%s.",
            project_id,
            scale_factor,
            unit_label,
        )
        return new_scale

    async def verify_geometry(
        self,
        project_id: str,
        corrections: Optional[list[dict]] = None,
        notes: str = "",
    ) -> dict:
        """
        Apply optional geometry corrections and advance to GEOMETRY_VERIFIED.

        This is Safety Gate 1.  The engineer must call this (directly or via the
        router) before loading and analysis can proceed.

        Parameters
        ----------
        project_id : str
        corrections : list[dict] | None
            Member-level corrections to apply to the cached geometry.
        notes : str
            Engineer confirmation notes.

        Returns
        -------
        dict
            ``{status, member_count, verified_at}``

        Raises
        ------
        ValueError
            If no parsed geometry exists for this project.
        """
        parsed = _store.get_parsed(project_id)
        if parsed is None:
            raise ValueError(
                f"Cannot verify geometry for project '{project_id}': "
                "no parsed data found."
            )

        if corrections:
            parsed["user_corrections"] = corrections
            _store.set_parsed(project_id, parsed)

        await project_store.advance_status(project_id, ProjectStatus.GEOMETRY_VERIFIED)
        scale = _store.get_scale(project_id) or {}
        self._schedule_db_save(self._db_save_geometry(project_id, parsed, scale))
        member_count = len(parsed.get("members", []))

        logger.info(
            "Geometry verified for project %s: %d member(s). Notes: %s",
            project_id,
            member_count,
            notes or "(none)",
        )
        return {
            "status": "verified",
            "member_count": member_count,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    def register_geometry(self, project_id: str, data: dict) -> None:
        """
        Directly inject parsed geometry (for testing or manual entry).

        Parameters
        ----------
        project_id : str
        data : dict
            Structural JSON to store.
        """
        _store.set_parsed(project_id, data)
        if "scale" in data:
            _store.set_scale(project_id, data["scale"])

    def clear(self, project_id: str) -> None:
        """
        Remove all cached geometry and scale data for a project.

        Parameters
        ----------
        project_id : str
        """
        _store.clear(project_id)

    # ── DB persistence helpers ────────────────────────────────────────────────

    async def _db_save_geometry(self, project_id: str, geometry: dict, scale: dict) -> None:
        """Upsert parsed geometry and scale to ProjectGeometry. Silent no-op if DB unavailable."""
        from config import settings
        if settings.PROJECT_STORE_BACKEND != "postgres":
            return
        try:
            from db.session import get_session_maker
            from db.models.project import ProjectGeometry
            from sqlalchemy import select

            session_maker = get_session_maker()
            async with session_maker() as session:
                row = (await session.execute(
                    select(ProjectGeometry).where(ProjectGeometry.project_id == project_id)
                )).scalar_one_or_none()

                geo_str = json.dumps(geometry)
                scale_str = json.dumps(scale)
                now = datetime.now(timezone.utc)

                if row:
                    row.geometry = geo_str
                    row.scale_json = scale_str
                    row.updated_at = now
                else:
                    session.add(ProjectGeometry(
                        project_id=project_id,
                        geometry=geo_str,
                        scale_json=scale_str,
                    ))
                await session.commit()
        except RuntimeError:
            pass  # DATABASE_URL not configured
        except Exception as exc:
            logger.warning("DB geometry save failed for project %s: %s", project_id, exc)

    def _schedule_db_save(self, coro) -> None:
        """Schedule a DB-write coroutine on the running event loop (fire-and-forget)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(coro)
        except RuntimeError:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
file_service = FileService()
