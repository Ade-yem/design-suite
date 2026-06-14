"""
services/agents/analyst.py  (Analyst Agent)
============================================
Analyst Agent node — the "Global Physics" of the pipeline.

Responsibilities
----------------
1. Gather *design considerations* conversationally once geometry is confirmed:
   building type / purpose, whether it is multi-storey and how many storeys,
   typical storey height, and any known dead loads / soil / material context.
   This qualitative project profile is what governs the loading.
2. Reason from those considerations to code-compliant load parameters —
   in particular, derive the characteristic imposed load Qk from the building's
   occupancy via the standard occupancy table rather than asking for it directly.
   Uses the LLM to extract structured data from natural language; never invents
   required values — asks for missing fields.
3. Validate the resulting load definition via the loading service before submit.
4. Run load combinations and trigger the analysis engine.
5. Stream live progress to the IDE left-panel status log.
6. Handle the re-analysis loop when the Designer sends back failed members
   due to self-weight changes.
7. Present analysis results with a clear narrative summary.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.state import StructuralDesignState
from agents import _get_llm


logger = logging.getLogger(__name__)


# Required design considerations, gathered before loads are assembled.
# Nothing here is assumed — every field is asked of the engineer.  Each entry is
# (dotted_path, domain, question).  ``num_storeys`` is auto-set to 1 only when the
# engineer explicitly states the building is single-storey.
_REQUIRED_FIELDS: list[tuple[str, str, str]] = [
    # ── Design basis ──
    ("design_working_life_years", "Design basis",
     "Design working life in years (e.g. 50 for ordinary buildings)"),
    # ── Geometry / structural form ──
    ("num_storeys", "Geometry",
     "Is it multi-storey, and how many storeys / floor levels?"),
    ("storey_height_m", "Geometry",
     "Typical clear storey height (m)"),
    ("is_braced", "Geometry",
     "Is the frame braced (stability from cores/shear walls) or unbraced/sway?"),
    # ── Materials ──
    ("materials.concrete_grade", "Materials",
     "Concrete grade — e.g. C30/37 (EC2) or grade 30 (BS 8110)"),
    ("materials.fy_main_MPa", "Materials",
     "Main reinforcement characteristic yield strength fy / fyk (MPa), e.g. 500"),
    ("materials.fy_link_MPa", "Materials",
     "Shear-link characteristic yield strength fyv / fywk (MPa), e.g. 500"),
    ("materials.unit_weight_kNm3", "Materials",
     "Reinforced-concrete unit weight (kN/m³), e.g. 25"),
    # ── Durability & fire ──
    ("durability.exposure_class", "Durability & fire",
     "Exposure class — e.g. XC1 (dry/internal), XC3/XC4, XD, XS; "
     "or BS 8110 condition (mild / moderate / severe)"),
    ("durability.fire_resistance_min", "Durability & fire",
     "Required fire resistance period in minutes, e.g. 60 / 90 / 120"),
    ("durability.nominal_cover_mm", "Durability & fire",
     "Nominal cover to reinforcement c_nom (mm)"),
    # ── Loading ──
    ("occupancy_category", "Loading",
     "Building use / occupancy (residential, office, retail, car park, roof, …) "
     "— this sets the imposed load Qk"),
    ("dead_loads.finishes_kNm2", "Loading",
     "Floor finishes (kN/m²) — enter 0 if none"),
    ("dead_loads.screed_kNm2", "Loading",
     "Screed (kN/m²) — enter 0 if none"),
    ("dead_loads.services_kNm2", "Loading",
     "M&E services (kN/m²) — enter 0 if none"),
    ("dead_loads.partitions_kNm2", "Loading",
     "Partition allowance (kN/m²) — enter 0 if none"),
]

# Conditional requirement: soil bearing capacity is only required when the parsed
# geometry actually contains foundation members.
_GEOTECH_FIELD = (
    "geotech.bearing_capacity_kPa", "Geotechnical",
    "Allowable / safe soil bearing capacity (kN/m²)",
)

_FIELD_METADATA: dict[str, dict[str, Any]] = {
    "design_working_life_years": {
        "type": "number",
        "label": "Design working life (years)",
        "default": 50,
    },
    "num_storeys": {
        "type": "number",
        "label": "Number of storeys",
        "default": 1,
    },
    "storey_height_m": {
        "type": "number",
        "label": "Typical clear storey height (m)",
        "default": 3.0,
    },
    "is_braced": {
        "type": "boolean",
        "label": "Braced stability?",
        "default": True,
    },
    "materials.concrete_grade": {
        "type": "select",
        "label": "Concrete grade",
        "options": ["C20/25", "C25/30", "C30/37", "C32/40", "C35/45", "C40/50"],
        "default": "C30/37",
    },
    "materials.fy_main_MPa": {
        "type": "number",
        "label": "Main bar yield fy (MPa)",
        "default": 500,
    },
    "materials.fy_link_MPa": {
        "type": "number",
        "label": "Link yield fyv (MPa)",
        "default": 500,
    },
    "materials.unit_weight_kNm3": {
        "type": "number",
        "label": "RC unit weight (kN/m³)",
        "default": 25,
    },
    "durability.exposure_class": {
        "type": "select",
        "label": "Exposure class / condition",
        "options": ["XC1", "XC2", "XC3", "XC4", "XD1", "XD2", "XD3", "XS1", "XS2", "XS3", "Mild", "Moderate", "Severe"],
        "default": "XC1",
    },
    "durability.fire_resistance_min": {
        "type": "select",
        "label": "Fire resistance (min)",
        "options": [30, 60, 90, 120, 180, 240],
        "default": 60,
    },
    "durability.nominal_cover_mm": {
        "type": "number",
        "label": "Nominal cover c_nom (mm)",
        "default": 25,
    },
    "occupancy_category": {
        "type": "select",
        "label": "Occupancy / building use",
        "options": ["residential", "office", "retail", "roof_accessible", "roof_non_accessible", "stairs", "custom"],
        "default": "office",
    },
    "dead_loads.finishes_kNm2": {
        "type": "number",
        "label": "Finishes dead load (kN/m²)",
        "default": 1.0,
    },
    "dead_loads.screed_kNm2": {
        "type": "number",
        "label": "Screed dead load (kN/m²)",
        "default": 0.0,
    },
    "dead_loads.services_kNm2": {
        "type": "number",
        "label": "Services dead load (kN/m²)",
        "default": 0.5,
    },
    "dead_loads.partitions_kNm2": {
        "type": "number",
        "label": "Partitions dead load (kN/m²)",
        "default": 1.0,
    },
    "geotech.bearing_capacity_kPa": {
        "type": "number",
        "label": "Soil bearing capacity (kN/m²)",
        "default": 150,
    }
}

# Nested dict keys that are deep-merged across dialogue turns.
_NESTED_GROUPS: tuple[str, ...] = ("materials", "durability", "dead_loads", "geotech")

# Dead-load component keys carried from the discovery dialogue into the
# load definition (the loading engine supplies its own defaults for any absent).
_DEAD_LOAD_KEYS: tuple[str, ...] = (
    "finishes_kNm2", "screed_kNm2", "services_kNm2", "partitions_kNm2", "cladding_kNm",
)

# Maximum self-weight convergence iterations before issuing a warning
_MAX_ITERATIONS = 5


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_path(data: dict, dotted: str) -> Any:
    """Return the value at a dotted path, or ``None`` if any segment is absent."""
    val: Any = data
    for key in dotted.split("."):
        if not isinstance(val, dict):
            return None
        val = val.get(key)
    return val


def _deep_merge_parameters(base: dict, incoming: dict) -> dict:
    """
    Merge freshly-extracted values onto the running profile.

    Only non-null values overwrite; the recognised nested groups (materials,
    durability, dead_loads, geotech) are merged one level deep so the engineer
    can supply them across multiple turns.
    """
    for key, value in incoming.items():
        if value is None:
            continue
        if key in _NESTED_GROUPS and isinstance(value, dict):
            merged = dict(base.get(key) or {})
            merged.update({k: v for k, v in value.items() if v is not None})
            base[key] = merged
        else:
            base[key] = value
    return base


def _build_considerations_prompt(design_code: str) -> str:
    """
    Opening prompt that kicks off the design-considerations dialogue.

    Parameters
    ----------
    design_code : str
        Active design code, surfaced so the engineer knows the basis.

    Returns
    -------
    str
        Concise welcome message directing the engineer to the interactive form.
    """
    return (
        "**Geometry confirmed.** Please fill in the interactive design parameters form below "
        f"to specify materials, durability, and loading requirements (basis: **{design_code}**)."
    )


def _considerations_extraction_prompt(message: str, design_code: str) -> str:
    """
    Build the LLM prompt that maps the engineer's description to parameters.

    Parameters
    ----------
    message : str
        The engineer's natural-language project description.
    design_code : str
        Active design code (already chosen at project creation).

    Returns
    -------
    str
        Extraction prompt instructing the model to extract, never invent.
    """
    return (
        "You are a senior structural engineer extracting a project brief from the "
        f"client engineer's description. The design code is {design_code}.\n"
        "Return ONLY a valid JSON object. Set any value not explicitly stated or "
        "clearly implied to null — do NOT invent, default or assume.\n\n"
        "Map the building usage to the closest occupancy_category from this set:\n"
        "  residential | office | retail | roof_accessible | "
        "roof_non_accessible | stairs | custom\n"
        "Guidance: flats/apartments/houses→residential; offices→office; "
        "shops/malls/showrooms→retail; schools/classrooms→office; "
        "warehouses/storage/car parks→custom. Use 'custom' only when nothing fits, "
        "and then also fill imposed_qk_kNm2 if a value is stated.\n\n"
        "Concrete grade: for 'C30/37' set materials.fck_MPa=30 and materials.fcu_MPa=37. "
        "For BS 8110 'grade 30' / 'C30' set materials.fcu_MPa=30. Only convert between "
        "cube and cylinder strength using the standard C{fck}/{fcu} class pairs; "
        "otherwise leave the counterpart null. Always echo the raw grade string in "
        "materials.concrete_grade.\n\n"
        "Schema (use null for anything not stated):\n"
        "  building_type (str), building_purpose (str)\n"
        "  occupancy_category (one of the set above)\n"
        "  is_multistorey (bool), num_storeys (int), storey_height_m (float)\n"
        "  is_braced (bool, true=braced, false=unbraced/sway)\n"
        "  design_working_life_years (int)\n"
        "  materials: {concrete_grade (str), fck_MPa (float), fcu_MPa (float), "
        "fy_main_MPa (float), fy_link_MPa (float), unit_weight_kNm3 (float)}\n"
        "  durability: {exposure_class (str), fire_resistance_min (int, minutes), "
        "nominal_cover_mm (float)}\n"
        "  dead_loads: {finishes_kNm2 (float), screed_kNm2 (float), "
        "services_kNm2 (float), partitions_kNm2 (float), cladding_kNm (float)}\n"
        "  imposed_qk_kNm2 (float, only if explicitly stated — otherwise null, "
        "it will be derived from occupancy)\n"
        "  roof_qk_kNm2 (float, optional)\n"
        "  geotech: {bearing_capacity_kPa (float)}\n\n"
        f"Description: {message}"
    )


def _has_footings(parsed_json: dict) -> bool:
    """True when the parsed geometry contains any foundation member."""
    return any(
        m.get("member_type") == "footing"
        for m in (parsed_json or {}).get("members", [])
    )


def _extract_missing_consideration_fields(
    params: dict, parsed_json: Optional[dict] = None
) -> list[str]:
    """
    Identify required design-consideration fields that are still unknown.

    Single-storey buildings default ``num_storeys`` to 1 (mutating ``params``)
    so the engineer is not asked a storey count that is implied.  ``0`` and
    ``False`` count as *provided*; only ``None``/absent counts as missing.

    Parameters
    ----------
    params : dict
        Project parameters accumulated so far across dialogue turns.
    parsed_json : dict | None
        Parsed geometry, used to decide whether geotechnical input is required.

    Returns
    -------
    list[str]
        Dotted paths of the still-missing required fields, in ask order.
    """
    # Imply single-storey count rather than asking for it.
    if params.get("num_storeys") is None and params.get("is_multistorey") is False:
        params["num_storeys"] = 1

    missing = [path for path, _, _ in _REQUIRED_FIELDS if _get_path(params, path) is None]

    if _has_footings(parsed_json or {}) and _get_path(params, _GEOTECH_FIELD[0]) is None:
        missing.append(_GEOTECH_FIELD[0])

    return missing


def _build_missing_consideration_question(missing: list[str]) -> str:
    """
    Build a concise prompt asking for the remaining missing brief inputs.

    Parameters
    ----------
    missing : list[str]
        Dotted paths of missing fields.

    Returns
    -------
    str
        Concise message prompting the engineer to fill out the form.
    """
    return "Please complete the remaining required design parameters in the form below."


def _build_load_definition_from_parameters(
    params: dict, design_code: str, qk: float
) -> dict:
    """
    Assemble a load definition from gathered considerations and the derived Qk.

    Parameters
    ----------
    params : dict
        Confirmed project parameters.
    design_code : str
        Active design code.
    qk : float
        Characteristic imposed floor load (kN/m²), derived or explicit.

    Returns
    -------
    dict
        Payload matching ``LoadDefinitionRequest`` shape.
    """
    dead = params.get("dead_loads") or {}
    dead_loads = {k: dead[k] for k in _DEAD_LOAD_KEYS if dead.get(k) is not None}

    imposed: dict[str, Any] = {"floor_qk_kNm2": qk}
    if params.get("roof_qk_kNm2") is not None:
        imposed["roof_qk_kNm2"] = float(params["roof_qk_kNm2"])

    load_def: dict[str, Any] = {
        "design_code": design_code,
        "occupancy_category": params.get("occupancy_category", "office"),
        "imposed_loads": imposed,
    }
    if dead_loads:
        load_def["dead_loads"] = dead_loads
    return load_def


def _material_meta_from_parameters(params: dict) -> dict:
    """
    Map gathered materials / durability into per-member geometry ``meta`` keys.

    These are the keys the design suite and self-weight calculation read off each
    member (``cover_mm``, ``fcu_MPa``/``fck_MPa``, ``fy_MPa``, ``fyv_MPa``,
    ``gamma_conc_kNm3``, plus exposure/fire context).
    """
    mats = params.get("materials") or {}
    dur = params.get("durability") or {}
    meta: dict[str, Any] = {}

    if dur.get("nominal_cover_mm") is not None:
        meta["cover_mm"] = float(dur["nominal_cover_mm"])
    if mats.get("fcu_MPa") is not None:
        meta["fcu_MPa"] = float(mats["fcu_MPa"])
    if mats.get("fck_MPa") is not None:
        meta["fck_MPa"] = float(mats["fck_MPa"])
    if mats.get("fy_main_MPa") is not None:
        meta["fy_MPa"] = meta["fyk_MPa"] = float(mats["fy_main_MPa"])
    if mats.get("fy_link_MPa") is not None:
        meta["fyv_MPa"] = float(mats["fy_link_MPa"])
    if mats.get("unit_weight_kNm3") is not None:
        meta["gamma_conc_kNm3"] = float(mats["unit_weight_kNm3"])
    if dur.get("exposure_class"):
        meta["exposure_class"] = dur["exposure_class"]
    if dur.get("fire_resistance_min") is not None:
        meta["fire_resistance_min"] = int(dur["fire_resistance_min"])

    return meta


async def _propagate_material_meta(project_id: str, params: dict) -> None:
    """
    Write the project-level materials/durability into every member's ``meta``.

    Uses ``setdefault`` so any pre-existing per-member value is preserved.  This
    is what makes the gathered materials actually reach the design suite and the
    self-weight calculation rather than being collected and ignored.
    """
    meta_updates = _material_meta_from_parameters(params)
    if not meta_updates:
        return
    try:
        from services.files import file_service
        parsed = await file_service.get_parsed(project_id)
    except Exception as exc:
        logger.warning("Could not load geometry to apply materials for %s: %s", project_id, exc)
        return

    for member in parsed.get("members", []):
        meta = member.setdefault("meta", {})
        for key, value in meta_updates.items():
            meta.setdefault(key, value)

    try:
        from services.files import file_service
        await file_service.register_geometry(project_id, parsed)
    except Exception as exc:
        logger.warning("Could not persist materials into geometry for %s: %s", project_id, exc)


def _build_parameters_summary(params: dict, design_code: str, qk: float) -> str:
    """
    Build the human-readable parameters card for engineer confirmation.

    Parameters
    ----------
    params : dict
        Confirmed project parameters.
    design_code : str
        Active design code.
    qk : float
        Derived/explicit characteristic imposed load (kN/m²).

    Returns
    -------
    str
        Markdown summary for the IDE chat panel.
    """
    num_storeys = params.get("num_storeys", 1)
    multistorey = "Yes" if (params.get("is_multistorey") or num_storeys > 1) else "No"
    building = params.get("building_type") or params.get("building_purpose") or "—"
    braced = "braced" if params.get("is_braced", True) else "unbraced / sway"
    mats = params.get("materials") or {}
    dur = params.get("durability") or {}
    dead = params.get("dead_loads") or {}

    lines = [
        "### 📋 Confirmed Project Parameters",
        "",
        f"- **Design code:** {design_code}",
        f"- **Building:** {building} — {multistorey} multi-storey "
        f"(**{num_storeys}** storey(s)), {braced}",
    ]
    if params.get("storey_height_m"):
        lines.append(f"- **Clear storey height:** {params['storey_height_m']} m")
    if params.get("design_working_life_years"):
        lines.append(f"- **Design working life:** {params['design_working_life_years']} years")

    grade = mats.get("concrete_grade") or "—"
    lines.append(
        f"- **Materials:** concrete {grade}, main steel {mats.get('fy_main_MPa', '—')} MPa, "
        f"links {mats.get('fy_link_MPa', '—')} MPa, "
        f"γ_conc {mats.get('unit_weight_kNm3', '—')} kN/m³"
    )
    lines.append(
        f"- **Durability & fire:** exposure {dur.get('exposure_class', '—')}, "
        f"fire {dur.get('fire_resistance_min', '—')} min, "
        f"cover {dur.get('nominal_cover_mm', '—')} mm"
    )
    lines.append(
        f"- **Occupancy:** {params.get('occupancy_category', 'office')} → "
        f"**imposed Qk = {qk:g} kN/m²** (standard occupancy table)"
    )
    if dead:
        dead_str = ", ".join(f"{k.replace('_kNm2', '').replace('_kNm', '')}={v}" for k, v in dead.items())
        lines.append(f"- **Superimposed dead loads:** {dead_str} kN/m²")
    if _get_path(params, "geotech.bearing_capacity_kPa") is not None:
        lines.append(f"- **Soil bearing capacity:** {params['geotech']['bearing_capacity_kPa']} kN/m²")

    lines.append("")
    lines.append(
        "I'll assemble the factored loads on this basis and run the analysis. "
        "**Confirm the loads** to proceed, or tell me what to adjust."
    )
    return "\n".join(lines)


def _build_analysis_narrative(results: dict) -> str:
    """
    Build a readable Markdown summary of analysis results.

    Parameters
    ----------
    results : dict
        ``AnalysisResultsResponse`` dict.

    Returns
    -------
    str
        Markdown summary for the IDE chat panel.
    """
    members = results.get("members", [])
    total = len(members)
    failed = [m["member_id"] for m in members if m.get("status") == "error"]
    passed = total - len(failed)

    lines = [
        f"**Structural Analysis Complete — {total} member(s)**\n",
        f"- ✅ Passed:  {passed}",
        f"- ❌ Errors:  {len(failed)}" if failed else "- ✅ Errors:  0",
    ]
    if failed:
        lines.append(f"\nFailed members: {', '.join(failed)}")

    lines.append(
        "\nResults are available in the Canvas panel. "
        "Confirm loads and **click Confirm Analysis** to proceed to design."
    )
    return "\n".join(lines)


# ─── Routing ──────────────────────────────────────────────────────────────────


def analyst_router(state: StructuralDesignState) -> str:
    """
    Route the analyst node's outgoing edge.

    While the analyst is still gathering the design brief / load inputs it has
    not completed analysis, so the run should **end** — the next engineer chat
    message then re-enters the analyst from the graph entry point.  (LangGraph
    resumes a *completed* thread from the start, but would resume an
    *interrupted* one straight into the downstream gate, swallowing the reply.)
    Once analysis is complete it proceeds to the loading-confirmation gate.

    Returns
    -------
    str
        ``"analysis_done"`` once analysis has run, else ``"awaiting_input"``.
    """
    return "analysis_done" if state.get("analysis_complete") else "awaiting_input"


# ─── Node ─────────────────────────────────────────────────────────────────────


async def analyst_node(state: StructuralDesignState) -> dict:
    """
    Analyst Agent LangGraph node.

    Entry conditions:
    - ``geometry_verified = True`` (Gate 1 passed)
    - OR ``reanalysis_triggered = True`` (Designer feedback loop)

    Parameters
    ----------
    state : StructuralDesignState
        Current pipeline state.

    Returns
    -------
    dict
        Partial state update.
    """
    project_id = state["project_id"]
    log_entry = {
        "agent": "analyst",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logs: list[dict] = []

    # ── Re-analysis branch ────────────────────────────────────────────────────
    if state.get("reanalysis_triggered"):
        return await _handle_reanalysis(state, log_entry)

    # ── Design considerations + load collection ───────────────────────────────
    # After geometry confirmation the Analyst first profiles the project
    # (building type, storeys, purpose) and reasons to the load parameters
    # before any combination is assembled.
    if not state.get("load_definition"):
        return await _collect_design_considerations(state, log_entry)

    # ── Run combinations ──────────────────────────────────────────────────────
    try:
        from services.loading import loading_service
        if state.get("load_definition"):
            await loading_service.define(project_id, state["load_definition"])
        await loading_service.run_combinations(project_id)
        logs.append({**log_entry, "status": "combinations_run"})
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Load combinations failed: {exc}")],
            "agent_logs": logs,
            "current_error": "INVALID_LOAD_INPUT",
        }

    # ── Run full analysis ─────────────────────────────────────────────────────
    try:
        from services.analysis import analysis_service
        logs.append({**log_entry, "status": "analysis_started"})

        # Define progress callback
        def _progress(step: str, pct: float) -> None:
            logs.append({
                **log_entry,
                "status": "analysis_running",
                "detail": step,
                "pct": pct,
            })

        await analysis_service.run(
            project_id,
            member_ids=None,
            options={"pattern_loading": True, "self_weight_iteration": True},
            progress_cb=_progress,
        )
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Analysis run failed: {exc}")],
            "agent_logs": logs,
            "current_error": "ANALYSIS_FAILED",
        }

    # ── Fetch results ─────────────────────────────────────────────────────────
    try:
        await analysis_service.ensure_cached(project_id)
        results = analysis_service.get_results(project_id)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Could not retrieve analysis results: {exc}")],
            "agent_logs": logs,
            "current_error": "ANALYSIS_FAILED",
        }

    failed_members = [
        m["member_id"] for m in results.get("members", []) if m.get("status") == "error"
    ]
    narrative = _build_analysis_narrative(results)

    return {
        "analysis_results": results,
        "analysis_complete": True,
        "failed_members_analysis": failed_members,
        "pipeline_status": "analysis_complete",
        "messages": [AIMessage(content=narrative)],
        "agent_logs": logs + [{**log_entry, "status": "complete"}],
        "current_error": None,
    }


async def _collect_design_considerations(
    state: StructuralDesignState, log_entry: dict
) -> dict:
    """
    Run the design-considerations dialogue, then reason to a load definition.

    Flow
    ----
    1. If the engineer has not yet replied to the opening prompt, present the full
       design questionnaire (building, materials, durability/fire, loading).
    2. LLM-extract a project brief from the reply (extract only, never invent),
       deep-merging with anything gathered on earlier turns.
    3. If any required field is missing, ask a domain-grouped follow-up rather
       than guessing — nothing is assumed on the engineer's behalf.
    4. Derive the imposed load Qk from occupancy via the loading service; for a
       ``custom`` occupancy with no stated Qk, ask for it explicitly.
    5. Assemble the load definition, validate (non-blocking) and submit; propagate
       the gathered materials into the geometry meta for the design suite.

    Parameters
    ----------
    state : StructuralDesignState
    log_entry : dict
        Base log entry for this agent invocation.

    Returns
    -------
    dict
        Partial state update.
    """
    from services.loading import loading_service

    messages = state.get("messages", [])
    design_code = state.get("design_code", "BS8110")
    params: dict = dict(state.get("project_parameters") or {})

    last = messages[-1] if messages else None

    # ── Step 1: open the dialogue if the engineer hasn't replied yet ──────────
    if not isinstance(last, HumanMessage):
        fields = []
        for path, domain, q in _REQUIRED_FIELDS:
            meta = _FIELD_METADATA.get(path, {})
            fields.append({
                "path": path,
                "domain": domain,
                "label": meta.get("label", path),
                "type": meta.get("type", "number"),
                "options": meta.get("options"),
                "default": meta.get("default"),
                "description": q,
            })
        parsed_json = state.get("parsed_structural_json") or {}
        if _has_footings(parsed_json):
            meta = _FIELD_METADATA.get(_GEOTECH_FIELD[0], {})
            fields.append({
                "path": _GEOTECH_FIELD[0],
                "domain": _GEOTECH_FIELD[1],
                "label": meta.get("label", _GEOTECH_FIELD[0]),
                "type": meta.get("type", "number"),
                "options": meta.get("options"),
                "default": meta.get("default"),
                "description": _GEOTECH_FIELD[2],
            })
        return {
            "messages": [AIMessage(
                content=_build_considerations_prompt(design_code),
                additional_kwargs={
                    "questionnaire": {
                        "title": "Design Parameters",
                        "description": "Please fill in the project parameters below.",
                        "fields": fields
                        }}
            )],
            "agent_logs": [{**log_entry, "status": "awaiting_design_considerations"}],
        }

    # ── Step 2: LLM extraction — extracts only, never invents ─────────────────
    try:
        raw = await _get_llm().ainvoke(
            _considerations_extraction_prompt(last.text, design_code),
            config={"tags": ["utility"]}
        )
        content = raw.text.replace("```json", "").replace("```", "").strip()
        extracted: dict = json.loads(content)
    except Exception:
        extracted = {}

    # Deep-merge new non-null values onto the running profile.
    params = _deep_merge_parameters(params, extracted)

    # ── Step 3: ask for any missing required considerations ───────────────────
    parsed_json = state.get("parsed_structural_json") or {}
    missing = _extract_missing_consideration_fields(params, parsed_json)
    if missing:
        fields = []
        lookup = {path: (domain, q) for path, domain, q in (*_REQUIRED_FIELDS, _GEOTECH_FIELD)}
        for path in missing:
            domain, q = lookup.get(path, ("Other", path))
            meta = _FIELD_METADATA.get(path, {})
            fields.append({
                "path": path,
                "domain": domain,
                "label": meta.get("label", path),
                "type": meta.get("type", "number"),
                "options": meta.get("options"),
                "default": meta.get("default"),
                "description": q,
            })
        return {
            "project_parameters": params,
            "messages": [AIMessage(
                content=_build_missing_consideration_question(missing),
                additional_kwargs={"questionnaire": {"fields": fields}}
            )],
            "agent_logs": [
                {**log_entry, "status": "design_considerations_incomplete", "detail": missing}
            ],
        }

    # ── Step 4: derive the imposed load Qk from occupancy ─────────────────────
    occupancy = params.get("occupancy_category", "office")
    qk = params.get("imposed_qk_kNm2")
    if qk is None:
        qk = loading_service.imposed_load_for(occupancy, design_code)
    if qk is None:
        return {
            "project_parameters": params,
            "messages": [AIMessage(content=(
                "I couldn't map that occupancy to a standard imposed load. "
                "What characteristic imposed floor load Qk (kN/m²) should I use?"
            ))],
            "agent_logs": [{**log_entry, "status": "awaiting_custom_qk"}],
        }

    # ── Step 5: assemble, validate and submit the load definition ─────────────
    load_def = _build_load_definition_from_parameters(params, design_code, float(qk))

    project_id = state["project_id"]
    try:
        validation = loading_service.validate(load_def)
        if not validation.valid:
            errors = validation.errors
            return {
                "project_parameters": params,
                "messages": [AIMessage(content=(
                    "⚠️ Load definition has errors:\n"
                    + "\n".join(f"- {e}" for e in errors)
                    + "\nPlease correct and resubmit."
                ))],
                "agent_logs": [{**log_entry, "status": "validation_failed", "detail": errors}],
            }
    except Exception:
        pass  # Validation failure is non-blocking if the service is unavailable

    await loading_service.define(project_id, load_def)

    # Push the gathered materials/durability into every member's geometry meta so
    # the design suite and self-weight calculation use them (not hard-coded defaults).
    await _propagate_material_meta(project_id, params)

    return {
        "project_parameters": params,
        "load_definition": load_def,
        "messages": [AIMessage(content=_build_parameters_summary(params, design_code, float(qk)))],
        "agent_logs": [{**log_entry, "status": "design_considerations_complete"}],
    }


async def _handle_reanalysis(
    state: StructuralDesignState, log_entry: dict
) -> dict:
    """
    Re-run analysis for failed members in the Designer → Analyst feedback loop.

    Parameters
    ----------
    state : StructuralDesignState
    log_entry : dict

    Returns
    -------
    dict
        Partial state update.
    """
    project_id = state["project_id"]
    failed = state.get("failed_members_design", [])
    iteration = state.get("iteration_count", 0)

    if iteration >= _MAX_ITERATIONS:
        return {
            "messages": [AIMessage(content=(
                f"⚠️ **Convergence Warning** — {iteration} iterations completed.\n\n"
                f"Members {', '.join(failed)} have not converged. "
                "Please review member sizes or loading manually."
            ))],
            "agent_logs": [{**log_entry, "status": "convergence_failed"}],
            "current_error": "CONVERGENCE_FAILED",
            "reanalysis_triggered": False,
        }

    # Re-run for failed members only
    try:
        from services.analysis import analysis_service
        await analysis_service.run(
            project_id,
            member_ids=failed,
            options={"self_weight_iteration": True},
        )
        await analysis_service.ensure_cached(project_id)
        new_results = analysis_service.get_results(project_id)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Re-analysis failed: {exc}")],
            "agent_logs": [{**log_entry, "status": "reanalysis_failed"}],
            "current_error": "ANALYSIS_FAILED",
        }

    # Merge new results into existing
    existing = state.get("analysis_results") or {"members": []}
    existing_map = {m["member_id"]: m for m in existing.get("members", [])}
    for m in new_results.get("members", []):
        existing_map[m["member_id"]] = m
    merged = {**existing, "members": list(existing_map.values())}

    return {
        "analysis_results": merged,
        "reanalysis_triggered": False,
        "iteration_count": iteration + 1,
        "agent_logs": [{
            **log_entry,
            "status": f"reanalysis_complete_iteration_{iteration + 1}",
        }],
        "messages": [AIMessage(content=(
            f"♻️ Re-analysis complete (iteration {iteration + 1}). "
            "Resuming design…"
        ))],
    }
