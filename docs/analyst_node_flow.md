# Analyst Node — Flow & Data Structures (Parser → Analyst → Analysis Engine)

**Status:** Design / engineering review document
**Scope:** The handoff from the Vision (Parser) Agent to the Analyst Agent, the data structures that cross that boundary, how the Analyst drives the analysis engine, and the gaps that must be closed before the analyst flow can be considered complete.

---

## 1. Executive Summary

The pipeline backbone is a LangGraph `StateGraph` (`agents/graph.py`) in which every node reads from and writes partial updates to a single shared object, `StructuralDesignState` (`agents/state.py`). The Parser (Vision) Agent populates geometry; the Analyst Agent collects loads, runs load combinations, and drives the structural analysis engine; results feed Gate 2 and then the Designer.

The **parser stage is largely complete**: it parses DXF/PDF, resolves unit ambiguity, and emits a list of classified structural members (columns, beams, slabs/voids) into `parsed_structural_json["members"]`. The **analyst node is wired end-to-end** (load collection → combinations → analysis → narrative) and the analysis engine + solvers exist, but several **structural correctness gaps** remain between the data the parser produces and what the analysis engine actually consumes. Those gaps are enumerated in §7 and are the substance of the remaining work.

Key headline findings:

- The parser produces **one single-span member per beam segment**; the engine therefore analyses every beam as a **simply-supported single span**, never as a continuous member, even though the sample drawings are continuous multi-span frames.
- A full 2D FEA solver (`global_solver.py`, `GlobalMatrixSolver`) **exists but is not wired into the engine** — `AnalysisEngine` routes beams only to the closed-form / moment-coefficient solvers. CLAUDE.md's claim that the analyst "runs 2D FEA" is not yet realised.
- **No vertical load take-down**: columns are analysed with the placeholder `N_uls = 1000 kN`, `M_uls = 0` baked in by the parser. Slab and beam reactions are never accumulated into columns.
- **Slabs ignore the assembled loads**: the slab routing path reads `n_uls` from geometry `meta` (which has no such key) and falls back to a hard-coded `10.0 kN/m²`, bypassing the load-combination output entirely.
- The `pattern_loading` and `self_weight_iteration` options the Analyst passes to `analysis_service.run()` are **accepted but never used** by the engine.

---

## 2. Where the Analyst sits in the graph

```
supervisor_agent
   │  (supervisor_router on pipeline_status)
   ├── "created" / "file_uploaded"   → vision_agent  (Parser)
   ├── "geometry_verified"           → analyst_agent
   ├── "loading_defined"             → analyst_agent
   ├── "analysis_complete"           → designer_agent
   └── ...

vision_agent ──► geometry_gate ──(confirmed)──► analyst_agent
                                  (waiting)────► END

analyst_agent ──► loading_gate ──(confirmed)──► designer_agent
                                 (waiting)─────► END

designer_agent ──(reanalysis_needed)──► analyst_agent   (self-weight loop)
```

The Analyst is reached in three distinct ways:

1. **First pass** — after Gate 1 (`geometry_verified = True`) the supervisor router maps `pipeline_status = "geometry_verified"` → `analyst`.
2. **Continued load collection** — once a load definition is partially supplied, status `loading_defined` also routes back to `analyst`.
3. **Re-analysis loop** — the Designer sets `reanalysis_triggered = True` and the `designer_router` returns `"reanalysis_needed"`, routing the graph edge back to `analyst_agent`.

`graph.py` registers the analyst as the node named `analyst_agent`, with a hard edge `analyst_agent → loading_gate`. `loading_gate` is in `_INTERRUPT_BEFORE`, so the graph **pauses for human confirmation** (Gate 2) after the Analyst finishes and before the Designer runs. Resumption is via `POST /api/v1/pipeline/{project_id}/resume`.

---

## 3. The Parser → Analyst data contract

### 3.1 What the parser writes to state

`parser_node` (`agents/parser.py`) returns a partial state update whose load-bearing field is:

```python
parsed_structural_json = {
    "members": [ ... ],          # the structural member list (see below)
    "entities": [ ... ],         # raw DXF entities (pre-classification)
    "scale": {factor, unit},
    "raw_entity_count": int,
    "parse_warnings": [ ... ],
}
unit_confirmation = {ambiguous, detected_unit, confidence, sample_dimensions}
pipeline_status   = "file_uploaded"
```

Gate 1 (`geometry_verification_gate`) then sets `geometry_verified = True` and calls `file_service.verify_geometry(...)`, which is what later lets `services.files.get_parsed()` return the confirmed geometry.

### 3.2 The member object — the unit of exchange

Each entry in `members` is a dict with this shape (column / beam / slab variants shown):

```jsonc
// COLUMN  (LLM stage-2 classification)
{
  "member_id": "C1-1", "member_type": "column", "type": "column",
  "start_point": null, "end_point": null,
  "center_point": {"x": 0.0, "y": 0.0},
  "boundary_polygon": null, "is_void": false,
  "meta": {"b": 225, "h": 225, "L_clear": 3.0,
           "end_condition": "fixed_fixed",
           "N_uls": 1000.0, "M_uls": 0.0},      // ⚠ placeholder loads
  "spans": [], "spans_m": []
}

// BEAM  (deterministic extraction from DXF LINE + nearest BeamText)
{
  "member_id": "1B1", "member_type": "beam", "type": "beam",
  "start_point": {"x": …, "y": …}, "end_point": {"x": …, "y": …},
  "center_point": null, "boundary_polygon": null, "is_void": false,
  "meta": {"b_mm": 225, "h_mm": 450, "L_clear": 5.5,
           "E": 30e6, "I": 0.00171},            // E in kPa, I in m⁴
  "spans": [{"span_id": "S1", "length_m": 5.5}],
  "spans_m": [5.5]                              // ⚠ always ONE span
}

// SLAB / VOID  (LLM stage-3, PDF-grounded)
{
  "member_id": "S1", "member_type": "slab", "type": "slab",
  "boundary_polygon": [{"x":…,"y":…}, …], "is_void": false,
  "meta": {"slab_type": "solid_slab", "Lx": 3.0, "Ly": 4.0,
           "thickness_mm": 150},
  "spans": [], "spans_m": [3.0, 4.0]
}
```

**How the parser builds these (3-stage pipeline in `_run_llm_member_extraction`):**

1. **Beams — deterministic.** DXF `LINE` geometry already carries correct coordinates; section (`b_mm × h_mm`) and label are read from nearby `BeamText` (regex `(\d{2,4})[xX×](\d{2,4})` and `(\d*[Bb]\d+)`). Default section `225×450 mm`. Stubs `< 0.6 m` (column-face artefacts) are dropped. Parallel edge-pairs are merged to a centreline (`_cluster_candidate_pairs`, `_deduplicate_beams`). No LLM — avoids overwhelming the model with ~90 featureless lines.
2. **Columns — LLM.** Closed rectangular/circular polylines are sent to Gemini for label assignment and section confirmation; defaults `L_clear = 3.0`, `end_condition = fixed_fixed`, `N_uls = 1000`, `M_uls = 0`.
3. **Slabs + voids — LLM, PDF-grounded.** A second Gemini call uses the already-extracted column grid + beam centrelines as a spatial framework and the reference PDF as visual ground truth; defaults `slab_type = solid_slab`, `thickness = 150 mm`.

### 3.3 Sample-data reality check

The `sample/` drawings (`1-2 layout.dxf`, `Floor-beam.dxf`, `Floor-beam.pdf`) are real multi-storey RC floor plans:

| Drawing | LINE | LWPOLYLINE | CIRCLE | TEXT | Notes |
|---|---|---|---|---|---|
| `1-2 layout.dxf` | 456 | 154 | 168 | 507 | Layers: `Beam`, `Column`, `AxisBalloons_*`, `BeamText`, `AxisText_*` |
| `Floor-beam.dxf` | 225 | 76 | 84 | 251 | Same layer scheme |

- **Beams** are drawn as **pairs of parallel lines** on the `Beam` layer, annotated in `BeamText` as e.g. `1B1 225x450 … 1B45 225x450` — i.e. all `225 mm × 450 mm`, IDs `B1…B45`.
- **Columns** are `LWPOLYLINE` rectangles (~`225×225 mm`) on the `Column` layer arranged on a grid.
- **Grid** is `CIRCLE` axis balloons + `AxisText` labels (letters `A…AJ`, numbers `1…17`).

**Implication:** these are **continuous beam grids on a column matrix**, with two-way slab panels bounded by the beams. The "correct" analysis is a 2D (ideally per-gridline) frame with load take-down to columns — not a bag of independent simply-supported beams. This is the central tension the remaining work must resolve (see §7).

---

## 4. Inside the Analyst node

`analyst_node(state)` (`agents/analyst.py`) is a three-way branch:

### 4.1 Branch A — Re-analysis (`reanalysis_triggered`)
Delegates to `_handle_reanalysis`:
- Guards against runaway loops with `_MAX_ITERATIONS = 5`; beyond that emits a `CONVERGENCE_FAILED` warning and clears the flag.
- Re-runs `analysis_service.run(project_id, member_ids=failed, options={self_weight_iteration: True})` for the failed members only, then **merges** the new member results into the cached set (`existing_map` keyed by `member_id`).
- Increments `iteration_count`, clears `reanalysis_triggered`, and lets the graph fall back through to the Designer.

### 4.2 Branch B — Load collection (`load_definition` missing)
Delegates to `_collect_load_inputs`:
- Reads the **last `HumanMessage`** in `state["messages"]`.
- Uses the LLM (`gemini-1.5-pro`, `temperature=0`) **only to extract** structured values from natural language into a load dict. Explicit instruction: *set anything not stated to `null`; never invent.*
- Required fields (`_REQUIRED_LOAD_FIELDS`): `design_code`, `occupancy_category`, `imposed_loads.floor_qk_kNm2`. Missing fields trigger a **targeted follow-up question** (`_build_missing_field_question`) rather than a default — the agent blocks until satisfied.
- Validates via `loading_service.validate(...)` (non-blocking if the API is down), then `loading_service.define(project_id, load_data)` persists the definition and returns. `load_definition` is now set, so the **next** entry into the node proceeds to Branch C.

### 4.3 Branch C — Combinations + analysis (`load_definition` present)
1. `loading_service.run_combinations(project_id)` — assembles factored member loads (see §5).
2. `analysis_service.run(project_id, member_ids=None, options={"pattern_loading": True, "self_weight_iteration": True}, progress_cb=_progress)` — runs the engine; `_progress` appends `analysis_running` log entries with `pct` for the IDE status stream.
3. `analysis_service.ensure_cached(...)` + `get_results(...)` — fetch the `AnalysisOutputSchema` dict.
4. Compute `failed_members_analysis` (members with `status == "error"`), build a Markdown narrative (`_build_analysis_narrative`), and return:

```python
{
  "analysis_results": results,
  "analysis_complete": True,
  "failed_members_analysis": [...],
  "pipeline_status": "analysis_complete",
  "messages": [AIMessage(narrative)],
  "agent_logs": [...],
  "current_error": None,
}
```

The graph then hits `loading_gate` (Gate 2) and pauses for the engineer to **Confirm Analysis**.

> **Note (ordering):** Gate 2 is described as "confirm factored loads", but in the current wiring the Analyst runs *both* combinations *and* full analysis before the gate interrupts. The engineer confirms after seeing analysis results. If the intent is to gate **before** spending compute on analysis, the combination and analysis steps should be split across two node visits. Flagged in §7.

---

## 5. Load assembly (what the Analyst feeds the engine)

`loading_service.run_combinations` → `_run_engine` (`services/loading.py`):

- Sums superimposed dead load `gk_base = finishes + screed + services + partitions` (with per-field fallbacks) and reads `qk_base = imposed.floor_qk_kNm2`.
- Picks the combination label by code: BS8110 `1.4Gk + 1.6Qk`, EC2 `1.35Gk + 1.5Qk`.
- For each member it factors loads via `LoadCombinationEngine.factor_loads(...)` for `ULS_DOMINANT` and `SLS_CHARACTERISTIC`, applying any `member_overrides` (`dead_extra_kNm2`, `imposed_override_kNm2`).
- Serialises per-member via `LoadSerializer.serialize_member` into a `MemberLoadOutput`:

```jsonc
{
  "member_id": "1B1", "member_type": "beam", "design_code": "BS8110",
  "spans": [{
     "span_id": "S1", "length_m": 5.5,
     "loads": {"udl_gk": 3.8, "udl_qk": 2.5,
               "n_uls": 9.32, "n_sls": 6.3, "point_loads": []},
     "pattern_loading_flag": false   // true only when raw_spans >= 3
  }],
  "combination_used": "1.4Gk + 1.6Qk", "source_slabs": [], ...
}
```

**Important:** the per-member UDL here is **per unit area carried directly as a line load** (`gk`, `qk` in kN/m²-derived terms). There is **no tributary-width / slab-to-beam distribution** and **no beam-reaction-to-column take-down**. Every member gets the same area-derived intensity. This is the loading-side half of the take-down gap in §7.

---

## 6. The analysis engine & solvers

`analysis_service.run` builds two lookups — `load_members` (from combination output) and `parsed_members` (geometry, for `meta`) — then, in a thread pool, loops member IDs and calls:

```python
engine.analyze_member(MemberLoadOutput(**load_member_data), geometry_meta)
```

where `geometry_meta = parsed_members[mid]["meta"]`. Results are stored as `AnalysisOutputSchema`-shaped dicts:

```jsonc
{
  "analysis_id": "ANA-XXXXXXXX", "design_code": "BS8110",
  "member_count": N, "generated_at": "...",
  "members": [ MemberAnalysisResult, ... ]
}
```

`AnalysisEngine.analyze_member` (`core/analysis/engine.py`) routes on `member_type`:

| Type | Router | Solver | Method | Loads source |
|---|---|---|---|---|
| beam (1 span) | `_route_beam` | `SimplySupportedBeamSolver` | closed-form | `span.loads["n_uls"]` ✅ |
| beam (≥2 spans) | `_route_beam` | `MomentCoefficientSolver` | BS8110 coefficients | `max(span n_uls)` ✅ |
| slab (solid/2-way) | `_route_slab` | `TwoWaySlabSolver` | BS8110 Table 3.14 | `meta["n_uls"]` ⚠ default 10.0 |
| slab (flat) | `_route_slab` | `FlatSlabSolver` | punching, closed-form | `meta["V_Ed"]` ⚠ default 0 |
| slab (ribbed) | `_route_slab` | `RibbedSlabSolver` | T-beam closed-form | `meta["n_uls"]` ⚠ default 10.0 |
| column | `_route_column` | `ColumnSolver` | BS8110 slenderness, closed-form | `meta["N_uls"/"M_uls"]` ⚠ placeholder |
| wall | `_route_wall` | `WallSolver` | BS8110/EC2 slenderness | `meta` defaults |
| footing | `_route_footing` | `PadFootingSolver` | closed-form | `meta` defaults |
| staircase | `_route_staircase` | `StaircaseSolver` | closed-form | `meta` defaults |

### 6.1 Solver capabilities (already implemented)
- **`SimplySupportedBeamSolver`** — superposition of UDL + point loads; `M=wL²/8`, `V=wL/2`, `δ=5wL⁴/384EI`; SLS deflection vs `span/250`; full `calculation_trace`.
- **`MomentCoefficientSolver`** — BS8110 Table 3.5 coefficients (`0.09FL`/`0.066FL` sagging, `−0.10FL`/`−0.086FL` hogging; shears `0.45F/0.60F/0.50F`).
- **`ColumnSolver`** — effective-length β (fixed-fixed 0.65 / fixed-pinned 0.80 / pinned 1.0), slenderness λ classification, minimum eccentricity `max(h/20, 20 mm)`, additional moment for slender columns.
- **`TwoWaySlabSolver` / `FlatSlabSolver` / `RibbedSlabSolver` / `WaffleSlabSolver`** — BS8110 Table 3.14 α-coefficients; flat-slab punching at control perimeter (EC2 2d / BS8110 1.5d).
- **`WallSolver`**, **`StaircaseSolver`**, **`PadFootingSolver`** etc. — closed-form, code-aware.
- **`GlobalMatrixSolver`** (`global_solver.py`) — a complete 2D Euler-Bernoulli frame matrix-stiffness solver (per-node 3 DOF, element `k`, transformation `T`, fixed-end forces from UDL, partitioned `K_ff D_f = F_f`, reactions + internal end forces). **Fully written, not yet called by the engine.**

### 6.2 Output contract (`models/analysis/schema.py`)
`MemberAnalysisResult` carries everything the Designer needs: `stress_resultants` (`M_max_sagging/hogging`, `V_max`, `N_axial`, `deflection_max`), `critical_sections`, `reactions_kN`, `governing_pattern`, `SLS_checks`, `calculation_trace` (step / formula / inputs / result / `clause_reference`), `warnings`, `flags`. This schema is solid and should remain the stable interface to the Designer.

---

## 7. Gaps & required work (the actual to-do)

The plumbing works; the **structural fidelity** is the gap. In rough priority:

1. **Continuity is lost at the parser boundary.** Each beam segment becomes a single-span member, so `_route_beam` always takes the simply-supported path and the `MomentCoefficientSolver` / `GlobalMatrixSolver` paths are effectively dead for real drawings. *Fix:* either (a) group co-linear beam segments sharing a gridline into a multi-span `spans[]` member during/after parsing, or (b) assemble a per-gridline frame and feed `GlobalMatrixSolver`.

2. **2D FEA is not wired in.** `GlobalMatrixSolver` exists but `AnalysisEngine` never instantiates it. CLAUDE.md advertises "runs 2D FEA". *Fix:* add a frame-assembly routing path (nodes from column centroids + beam endpoints, elements from beams/columns, supports at column bases) and route continuous/framed members there; keep closed-form solvers as the fast path for isolated members.

3. **No vertical load take-down.** Columns analyse with `N_uls = 1000 kN`, `M_uls = 0` (parser placeholders); slab/beam reactions never reach columns. *Fix:* accumulate beam end-reactions (already produced by the solvers) into the columns they frame into, and slab panel loads into supporting beams via tributary areas, before `_route_column` runs. This requires an analysis ordering: slabs → beams → columns.

4. **Slabs ignore assembled loads.** `_route_slab` reads `meta["n_uls"]` (never set in geometry `meta`) and defaults to `10.0 kN/m²`, bypassing `loading_service` output. *Fix:* thread the per-member `load_data.spans[...].loads["n_uls"]` (or a panel pressure) into the slab solvers, and map parser `slab_type = "solid_slab"` to the engine's expected `"solid"`/`"flat"`/`"ribbed"` keys (currently mismatched, so everything falls to the two-way default).

5. **Unused analysis options.** `pattern_loading` and `self_weight_iteration` are passed by the Analyst but `analysis_service.run` never reads `opts`. Pattern loading is only a per-span boolean today. *Fix:* implement pattern-load envelopes in the multi-span path and an actual self-weight iteration loop, or drop the options to avoid implying behaviour that doesn't exist.

6. **Re-analysis uses stale geometry.** `_handle_reanalysis` re-runs failed members, but `geometry_meta` (`b`, `h`, `I`) comes from `parsed_members`, which the Designer's size changes don't update. Without refreshed sections/`member_overrides`, the loop can converge to the same numbers. *Fix:* have the Designer write updated sections back to the geometry/override store that the engine reads.

7. **Gate-2 semantics vs. compute ordering.** Gate 2 ("confirm loads") currently fires *after* full analysis. *Fix (if desired):* split combinations and analysis so the engineer confirms factored loads before the analysis run is spent.

8. **Engine robustness.** `_route_footing` returns `None` for non-pad footings (would crash `model_dump()` downstream); slab/flat-slab `V_Ed` defaults to 0 making punching trivially pass. Add explicit `skipped`/`warning` results rather than `None`.

---

## 8. Recommended target flow (analyst node)

```
Gate 1 confirmed
      │
      ▼
analyst_node ── load_definition? ──no──► ask engineer (LLM extract, block on missing)
      │ yes
      ▼
run_combinations  →  factored ULS/SLS per member (with tributary distribution)   [TODO §3,§5]
      │
      ▼
analysis ordering:  slabs ──► beams ──► columns
      │   slabs: TwoWay/Flat/Ribbed using real panel pressure        [TODO §4]
      │   beams: continuous spans → GlobalMatrixSolver (or coeffs)   [TODO §1,§2]
      │   columns: ColumnSolver with N,M from accumulated reactions  [TODO §3]
      ▼
AnalysisOutputSchema  →  state.analysis_results
      │
      ▼
loading_gate (Gate 2)  →  engineer confirms  →  designer_agent
```

This keeps the existing service/solver/schema architecture intact — the work is **routing and load-flow**, not a rewrite. The `MemberAnalysisResult` / `AnalysisOutputSchema` contract to the Designer is already correct and should be frozen.

---

## 9. File reference map

| Concern | File |
|---|---|
| Shared state | `apps/api/agents/state.py` |
| Graph wiring | `apps/api/agents/graph.py` |
| Routing | `apps/api/agents/supervisor.py` |
| Parser node | `apps/api/agents/parser.py` |
| Analyst node | `apps/api/agents/analyst.py` |
| Gates | `apps/api/agents/gates.py` |
| Loading service | `apps/api/services/loading.py` |
| Loading serializer / schema | `apps/api/core/loading/serializer.py`, `apps/api/models/loading/schema.py` |
| Analysis service | `apps/api/services/analysis.py` |
| Analysis engine (router) | `apps/api/core/analysis/engine.py` |
| Beam solvers | `apps/api/core/analysis/beam_solver.py` |
| 2D FEA (unwired) | `apps/api/core/analysis/global_solver.py` |
| Other solvers | `apps/api/core/analysis/{column,slab,footing,staircase,wall}_solver.py` |
| Analysis output schema | `apps/api/models/analysis/schema.py` |
| Sample drawings | `sample/1-2 layout.dxf`, `sample/Floor-beam.dxf`, `sample/Floor-beam.pdf` |
