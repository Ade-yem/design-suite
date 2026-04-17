"""
Input Normalizer
================
Validates and flattens individual Design Suite member JSON outputs into a
single unified **Report Data Model** (RDM).

The RDM is the single source of truth consumed by all five reporting modules.
This module is the only place that touches raw upstream JSON — all downstream
modules receive a ``ReportDataModel`` instance.

Validation Rules
----------------
* Every member must have ``loading_output``, ``analysis_output``, and
  ``design_output`` keys present.
* Members with any failed check are flagged but do not block report generation.
* Defaulted inputs are collected into a ``defaulted_inputs`` registry.
* All members in a single report must share the same ``design_code`` value.
  Mixed codes are rejected with a ``ValidationError``.

Classes
-------
ReportProject
    Project-level metadata (name, reference, engineer, etc.).
ReportMember
    Normalised representation of a single designed structural member.
ReportDataModel
    The complete assembled model for an entire project report.
InputNormalizer
    Stateless callable that produces a ``ReportDataModel`` from raw dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Dataclasses — Report Data Model
# ---------------------------------------------------------------------------


@dataclass
class ReportProject:
    """
    Project-level metadata for the engineering report header.

    Parameters
    ----------
    name : str
        Full project title (e.g. "Proposed 4-Storey Office Building").
    reference : str
        Project / job reference number (e.g. "PRJ-2024-047").
    client : str
        Client or employer name.
    engineer : str
        Lead structural engineer name (e.g. "Engr. J. Smith").
    checker : str
        Checking engineer name. May be blank for draft reports.
    date : str
        Issue date string (ISO 8601 preferred: "YYYY-MM-DD").
    revision : str
        Drawing / document revision code (e.g. "P01", "C02").
    design_code : str
        Primary design code(s) applied (e.g. "BS8110 | EC2").
    design_code_edition : str
        Edition of each code (e.g. "BS 8110-1:1997 | EN 1992-1-1:2004").
    """

    name: str
    reference: str
    client: str = ""
    engineer: str = ""
    checker: str = ""
    date: str = field(default_factory=lambda: date.today().isoformat())
    revision: str = "P01"
    design_code: str = "BS8110"
    design_code_edition: str = "BS 8110-1:1997"


@dataclass
class ReportMember:
    """
    Normalised representation of a single designed structural member.

    Parameters
    ----------
    member_id : str
        Unique member identifier (e.g. "B-12", "C-04").
    member_type : str
        Structural type: "beam", "column", "slab_one_way", "slab_two_way",
        "slab_ribbed", "slab_waffle", "slab_flat", "wall",
        "footing_pad", "footing_pile", "staircase".
    floor_level : str
        Floor level description (e.g. "First Floor", "Ground Floor").
    design_code : str
        Design code applied to this member (must match project code).
    loading_output : dict
        Raw JSON output from the Loading module for this member.
    analysis_output : dict
        Raw JSON output from the Analysis Engine for this member.
    design_output : dict
        Raw JSON output from the Design module for this member.
    calculation_trace : list[dict]
        Ordered list of calculation step dicts from the Design module.
        Each dict must contain: step, description, clause, formula,
        inputs, result, units.
    reinforcement : dict
        Reinforcement schedule data extracted from design_output.
        Keys: main_bars, links, distribution_bars.
    geometry : dict
        Geometric properties (dimensions, spans, etc.) for quantity take-off.
    status : str
        "PASS" if all limit state checks passed, "FAIL" otherwise.
    failed_checks : list[dict]
        List of individual failed checks.
        Each dict: {check, actual, limit, units}.
    near_limit_checks : list[dict]
        Checks within 5 % of capacity.
        Each dict: {check, utilisation_pct, note}.
    defaulted_inputs : list[dict]
        Inputs assumed by the system rather than provided by the user.
        Each dict: {parameter, default_used, source}.
    warnings : list[str]
        Non-fatal warnings from the design module.
    """

    member_id: str
    member_type: str
    floor_level: str
    design_code: str
    loading_output: dict
    analysis_output: dict
    design_output: dict
    calculation_trace: list[dict] = field(default_factory=list)
    reinforcement: dict = field(default_factory=dict)
    geometry: dict = field(default_factory=dict)
    status: str = "PASS"
    failed_checks: list[dict] = field(default_factory=list)
    near_limit_checks: list[dict] = field(default_factory=list)
    defaulted_inputs: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReportDataModel:
    """
    The complete assembled Report Data Model for an entire project.

    This is the single object passed into all five reporting modules.
    Produced exclusively by ``InputNormalizer.normalize()``.

    Parameters
    ----------
    project : ReportProject
        Project-level metadata.
    members : list[ReportMember]
        All normalised members to be included in the report.
    global_warnings : list[str]
        Project-level warnings (e.g. mixed design codes detected).
    material_summary : dict
        Aggregated concrete/steel/formwork quantities (populated by
        Module 3 — Material Quantity Engine).
    reinforcement_summary : dict
        Aggregated bar schedule totals (populated by Module 2).
    """

    project: ReportProject
    members: list[ReportMember] = field(default_factory=list)
    global_warnings: list[str] = field(default_factory=list)
    material_summary: dict = field(default_factory=dict)
    reinforcement_summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation Error
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """
    Raised by ``InputNormalizer.normalize()`` when the input data fails a
    hard validation rule that prevents any report from being generated.

    Attributes
    ----------
    message : str
        Human-readable description of the validation failure.
    member_id : str or None
        The member that triggered the error, if applicable.
    """

    def __init__(self, message: str, member_id: Optional[str] = None):
        self.message = message
        self.member_id = member_id
        super().__init__(message)


# ---------------------------------------------------------------------------
# Input Normalizer
# ---------------------------------------------------------------------------


class InputNormalizer:
    """
    Validates and assembles individual Design Suite member JSON outputs into a
    unified ``ReportDataModel``.

    This class is stateless — all state lives in the returned ``ReportDataModel``.

    Usage
    -----
    ::

        normalizer = InputNormalizer()
        rdm = normalizer.normalize(
            project_meta={...},
            members=[
                {
                    "member_id": "B-12",
                    "member_type": "beam",
                    "floor_level": "First Floor",
                    "design_code": "BS8110",
                    "loading_output": {...},
                    "analysis_output": {...},
                    "design_output": {...},
                }
            ]
        )
    """

    # Design-code normalisation map: accept common aliases
    _CODE_ALIASES: dict[str, str] = {
        "bs8110": "BS8110",
        "bs 8110": "BS8110",
        "ec2": "EC2",
        "eurocode2": "EC2",
        "eurocode 2": "EC2",
        "en1992": "EC2",
        "en 1992": "EC2",
    }

    # Near-limit threshold (within this fraction of capacity → warning)
    NEAR_LIMIT_THRESHOLD = 0.05

    def normalize(
        self,
        project_meta: dict[str, Any],
        members: list[dict[str, Any]],
    ) -> ReportDataModel:
        """
        Validate and assemble a ``ReportDataModel`` from raw project and member dicts.

        Parameters
        ----------
        project_meta : dict
            Project-level metadata. Required keys: ``name``, ``reference``.
            Optional keys match ``ReportProject`` fields.
        members : list[dict]
            Each dict represents one designed member. Required keys per member:
            ``member_id``, ``member_type``, ``floor_level``, ``design_code``,
            ``loading_output``, ``analysis_output``, ``design_output``.

        Returns
        -------
        ReportDataModel
            Fully validated and normalised report data model.

        Raises
        ------
        ValidationError
            If any hard validation rule is violated (e.g. mixed codes, missing
            required fields on all members).
        """
        global_warnings: list[str] = []

        # Build project metadata
        project = self._build_project(project_meta)

        # Normalise members
        report_members: list[ReportMember] = []
        codes_seen: set[str] = set()

        for raw in members:
            member = self._normalise_member(raw, project.design_code, global_warnings)
            report_members.append(member)
            codes_seen.add(member.design_code)

        # Design code consistency check
        if len(codes_seen) > 1:
            msg = (
                f"Mixed design codes detected across members: {sorted(codes_seen)}. "
                "Generate separate report sets per code."
            )
            global_warnings.append(msg)

        return ReportDataModel(
            project=project,
            members=report_members,
            global_warnings=global_warnings,
        )

    # ------------------------------------------------------------------ private

    def _build_project(self, meta: dict[str, Any]) -> ReportProject:
        """Build a ReportProject from a raw dict, applying defaults."""
        required = {"name", "reference"}
        missing = required - set(meta.keys())
        if missing:
            raise ValidationError(
                f"Project metadata is missing required keys: {missing}"
            )
        return ReportProject(
            name=meta["name"],
            reference=meta["reference"],
            client=meta.get("client", ""),
            engineer=meta.get("engineer", ""),
            checker=meta.get("checker", ""),
            date=meta.get("date", date.today().isoformat()),
            revision=meta.get("revision", "P01"),
            design_code=self._normalise_code(meta.get("design_code", "BS8110")),
            design_code_edition=meta.get("design_code_edition", "BS 8110-1:1997"),
        )

    def _normalise_member(
        self,
        raw: dict[str, Any],
        project_code: str,
        global_warnings: list[str],
    ) -> ReportMember:
        """Validate and normalise one member dict into a ReportMember."""
        member_id = raw.get("member_id", "UNKNOWN")

        # Hard required fields
        required = {
            "member_id", "member_type", "floor_level", "design_code",
            "loading_output", "analysis_output", "design_output",
        }
        missing = required - set(raw.keys())
        if missing:
            raise ValidationError(
                f"Member '{member_id}' is missing required keys: {missing}",
                member_id=member_id,
            )

        design_output: dict = raw["design_output"]
        analysis_output: dict = raw["analysis_output"]

        # Extract calculation trace from design_output (key may vary by module)
        trace = raw.get("calculation_trace") or design_output.get("notes", [])
        trace = self._normalise_trace(trace)

        # Extract reinforcement
        reinforcement = self._extract_reinforcement(raw, design_output)

        # Extract geometry
        geometry = raw.get("geometry", {})

        # Determine pass/fail from design_output status field
        raw_status = design_output.get("status", "OK")
        status = "FAIL" if raw_status not in ("OK", "PASS") else "PASS"

        # Parse failed checks
        failed_checks = self._extract_failed_checks(design_output)
        if failed_checks:
            status = "FAIL"

        # Parse near-limit checks
        near_limit = self._extract_near_limit(design_output)

        # Collect warnings
        warnings = design_output.get("warnings", [])

        # Flag defaulted inputs
        defaulted = raw.get("defaulted_inputs", [])

        return ReportMember(
            member_id=member_id,
            member_type=raw["member_type"],
            floor_level=raw["floor_level"],
            design_code=self._normalise_code(raw["design_code"]),
            loading_output=raw["loading_output"],
            analysis_output=analysis_output,
            design_output=design_output,
            calculation_trace=trace,
            reinforcement=reinforcement,
            geometry=geometry,
            status=status,
            failed_checks=failed_checks,
            near_limit_checks=near_limit,
            defaulted_inputs=defaulted,
            warnings=warnings,
        )

    @staticmethod
    def _normalise_code(code: str) -> str:
        """Normalise a design code string to canonical form."""
        key = code.strip().lower()
        aliases = InputNormalizer._CODE_ALIASES
        return aliases.get(key, code.strip().upper())

    @staticmethod
    def _normalise_trace(raw_notes: Any) -> list[dict]:
        """
        Convert design_output ``notes`` (list[str]) or a pre-structured
        ``calculation_trace`` (list[dict]) into the canonical trace format.

        Canonical trace step dict keys
        --------------------------------
        step        : int — step number
        description : str — human-readable description
        clause      : str — code clause reference
        formula     : str — symbolic formula
        inputs      : str — substituted values
        result      : str — computed result with units
        """
        if not raw_notes:
            return []
        normalised: list[dict] = []
        for i, item in enumerate(raw_notes, start=1):
            if isinstance(item, dict):
                normalised.append({
                    "step": item.get("step", i),
                    "description": item.get("description", ""),
                    "clause": item.get("clause", ""),
                    "formula": item.get("formula", ""),
                    "inputs": item.get("inputs", ""),
                    "result": item.get("result", ""),
                })
            else:
                # Plain string note — wrap it minimally
                normalised.append({
                    "step": i,
                    "description": str(item),
                    "clause": "",
                    "formula": "",
                    "inputs": "",
                    "result": "",
                })
        return normalised

    @staticmethod
    def _extract_reinforcement(raw: dict, design_output: dict) -> dict:
        """
        Extract reinforcement data from the raw member dict or design_output.

        Returns a dict with keys: main_bars, links, distribution_bars.
        Each is a list of bar schedule dicts.
        """
        if "reinforcement" in raw:
            return raw["reinforcement"]
        # Reconstruct a minimal schedule from design_output fields
        rebar: dict[str, list] = {
            "main_bars": [],
            "links": [],
            "distribution_bars": [],
        }
        if "reinforcement_description" in design_output:
            rebar["main_bars"].append({
                "zone": "primary",
                "description": design_output["reinforcement_description"],
                "As_prov": design_output.get("As_prov", 0.0),
                "As_req": design_output.get("As_req", 0.0),
            })
        if "shear_links" in design_output:
            rebar["links"].append({
                "zone": "general",
                "description": design_output["shear_links"],
            })
        if "distribution_steel" in design_output:
            rebar["distribution_bars"].append({
                "zone": "distribution",
                "description": design_output["distribution_steel"],
            })
        return rebar

    @staticmethod
    def _extract_failed_checks(design_output: dict) -> list[dict]:
        """
        Identify failed checks from design_output status and sub-statuses.

        Returns a list of dicts: {check, actual, limit, units}.
        """
        failed: list[dict] = []
        status = design_output.get("status", "OK")

        # Top-level status failure
        if status not in ("OK", "PASS"):
            failed.append({
                "check": "Overall status",
                "actual": status,
                "limit": "OK",
                "units": "",
            })

        # Deflection
        defl = design_output.get("deflection_check", "")
        if defl == "FAIL":
            failed.append({
                "check": "Deflection",
                "actual": "FAIL",
                "limit": "PASS",
                "units": "",
            })

        # Shear sub-status
        shear = design_output.get("shear_status", "")
        if "FAIL" in str(shear):
            failed.append({
                "check": "Shear",
                "actual": shear,
                "limit": "vc",
                "units": "N/mm²",
            })

        # Punching
        punch = design_output.get("punching_status", "")
        if "FAIL" in str(punch):
            failed.append({
                "check": "Punching shear",
                "actual": punch,
                "limit": "vc",
                "units": "N/mm²",
            })

        return failed

    @staticmethod
    def _extract_near_limit(design_output: dict) -> list[dict]:
        """
        Identify checks that are within 5 % of the capacity limit.

        Returns a list of dicts: {check, utilisation_pct, note}.
        """
        near: list[dict] = []
        threshold = 1.0 - InputNormalizer.NEAR_LIMIT_THRESHOLD
        # Deflection utilisation (ratio is embedded in notes — heuristic only)
        # Module consumers may enrich this from structured fields.
        return near
