# Test Suite Audit Report

**Date:** 2026-05-18  
**Auditor:** Senior QA / Backend Engineer review  
**Scope:** `apps/api/` — all test files and all backend source modules

---

## The Core Problem

The test suite has a structural split: pure-math calculation modules (solvers) have decent coverage, but every layer that connects them to the outside world — services, routers, agents, storage, reporting — has **zero tests**. The `ASGITransport` HTTP client creates an illusion of integration, but all requests land on in-memory dicts, never touching Postgres, Cloudinary, or Gemini.

---

## Section A: What Each Test File Actually Does

### Pure-math / Pure-Python (no IO, no mocks needed — these are fine)

| File | What it covers |
|---|---|
| `tests/unit/analysis/test_beam_solver.py` | Simply supported UDL/point load, BS8110 moment coefficients |
| `tests/unit/analysis/test_column_solver.py` | Short/slender classification, M_add |
| `tests/unit/analysis/test_global_solver.py` | 2D frame reactions, portal frame sway, singular matrix detection |
| `tests/unit/analysis/test_slab_solver.py` | Two-way moments, flat slab punching, ribbed load distribution |
| `tests/unit/analysis/test_footing_solver.py` | Pad footing area, bearing pressure, design moment |
| `tests/unit/design/test_beam_design_bs8110.py` / `test_bs8110_beam.py` | K, z, As, shear links — rectangular and flanged sections |
| `tests/unit/design/test_ec2_beam.py` | EC2 singly reinforced, shear links, deflection check |
| `tests/beam_8110/test_beam_design.py` + `test_formulas.py` + `test_analysis.py` | Deep beam, hogging, vc, torsion, anchorage formulas |
| `tests/test_slab_design.py`, `tests/slab/test_slab_design.py` | Basic reinforcement, deflection failure, shear failure |
| `tests/test_column_design.py` | Short and slender column, inadequate section |
| `tests/unit/drafting/test_beam_drawing_generator.py` | Bar positioning, cover bounds, scale consistency |

### Pseudo-integration (uses `AsyncClient(app=app)` but hits in-memory stores only)

- **`tests/conftest.py`**: The `async_client` fixture uses `ASGITransport` which looks like live HTTP but the app is wired to `project_store` (a Python dict), not Postgres. No real DB, no real files.
- **`tests/integration/test_loading_router.py`**: Tests a single Gate 403 response. All downstream tests are `@pytest.mark.skip`.
- **`tests/integration/test_loading_to_analysis.py`**: Three test methods, all `@pytest.mark.skip`. Zero coverage.

### Stub-based (defines a fake class in the test file itself)

- **`tests/unit/loading/test_load_combinations.py`**: The `LoadCombinationEngine` being tested is a **stub class written inside the test file**. The real `core.loading.load_combinations.LoadCombinationEngine` is never imported or tested.
- **`tests/unit/loading/test_slab_load_assembly.py`**: Same pattern — `SolidSlabLoadAssembler`, `RibbedSlabLoadAssembler`, `FlatSlabLoadAssembler` are all stubs defined in the test file, not the real assemblers.
- **`tests/unit/analysis/test_matrix_stiffness_solver.py`**: `MatrixStiffnessSolver` is a stub. The real global solver is tested separately in `test_global_solver.py`, but this test doesn't exercise it.
- **`tests/unit/analysis/test_moment_coefficient_solver.py`**: `MomentCoefficientSolver` is a stub.
- **`tests/unit/reporting/test_calc_trace_renderer.py`**: `CalcTraceRenderer` stub, not the real engine.

### Only real integration test in the suite

- **`tests/integration/test_vision_agent.py`**: Uses a real DXF file, makes real Gemini API calls, and registers members. This is the **only test that touches a live external service**.

### E2E tests — zero implementation

- **`tests/e2e/test_full_pipeline_bs8110.py`**: Has hand-calc benchmark values written in comments, but every test method is `@pytest.mark.skip`. No implementation.
- **`tests/e2e/test_canvas_interactions.py`**: Needs Playwright; all skipped.

### Auth tests (mocked correctly for unit scope)

- **`tests/test_auth.py`**: Tests `UserManager` with a `FakeSession` and `AsyncMock` email service. Covers org auto-creation, slug collision, forgot-password blocking. Scope is correct for a unit test but there are no HTTP-level auth flow tests at all.

---

## Section B: Source Modules With Zero Test Coverage

### Agents layer — entirely untested

| Module | What it does |
|---|---|
| `agents/graph.py` | LangGraph `StateGraph` definition, node wiring, entry point for every pipeline run |
| `agents/supervisor.py` | Router that decides which agent runs next |
| `agents/analyst.py` | FEA analysis agent node |
| `agents/designer.py` | Reinforcement design agent node + self-weight iteration loop |
| `agents/drafter.py` | SVG drawing primitives agent node |
| `agents/gates.py` | Hard-stop decision logic for all 4 gates |
| `agents/tools.py` | LangGraph tool definitions exposed to agents |
| `agents/state.py` | `StructuralDesignState` — no validation tests for field invariants |

### Services layer — entirely untested

| Module | What it does |
|---|---|
| `services/analysis.py` | Orchestrates member analysis, stores `AnalysisResult` |
| `services/design.py` | Orchestrates member design, handles overrides, stores `DesignResult` |
| `services/loading.py` | Sequences load combination computation |
| `services/files.py` | Parse job coordination, scale detection |

### Routers layer — entirely untested

`projects.py`, `files.py`, `analysis.py`, `design.py`, `drawings.py`, `reports.py`, `jobs.py` — none have any HTTP-level tests. `loading.py` has one gate-enforcement test but all meaningful endpoint tests are skipped.

### Core design — heavy gaps

| Code | Tested | Not Tested |
|---|---|---|
| BS8110 | Beam, column (basic), formulas, slab (basic) | Footing, wall, special slab, staircase |
| EC2 | Beam only | Column, footing, wall, slab, special slab, staircase |
| Common | — | `select_reinforcement.py`, `interaction.py` |

### Core loading

Real `LoadCombinationEngine` never tested. `special_slabs.py`, `vertical_loaders.py`, `staircase.py`, `tables.py`, `serializer.py` — all zero.

### Core parsing

`dxf_parser.py` and `pdf_parser.py` — no isolated unit tests. The vision agent integration test exercises the parser end-to-end but there are no tests for malformed files, edge cases, or scale detection.

### Core drawing

Only `BeamDrawingGenerator` tested. `ColumnDrawingGenerator`, `SlabDrawingGenerator`, `FootingDrawingGenerator`, `WallDrawingGenerator`, `StaircaseDrawingGenerator` — all zero.

### Core reporting — entire layer, zero tests

`CalcSheetEngine`, `BMDGenerator`, `SFDGenerator`, `RebarScheduleEngine`, `MaterialQuantityEngine`, `ComplianceReportEngine`, `PDFExportEngine` (WeasyPrint), `TemplateRenderer` (Jinja2), `InputNormalizer` — none tested.

### Storage and database

`project_store.py`, `job_store.py`, `file_handler.py`, `file_backends/` (Cloudinary + local), SQLAlchemy ORM models — zero tests. The in-memory store used in fixtures is not the SQLAlchemy-backed store that production uses.

### Auth layer

`auth/router.py` (JWT token generation, 2FA flow), `auth/backend.py`, `auth/dependencies.py`, `auth/auth_db.py`, Google OAuth flow — all untested at the HTTP level.

---

## Section C: Tests That Appear to Be Integration But Are Not

| Test | The Illusion | The Reality |
|---|---|---|
| `conftest.py` `async_client` | `ASGITransport(app=app)` looks like a live server | App uses `project_store` (Python dict), no Postgres, no Cloudinary |
| `test_loading_router.py` | Imports `async_client`, makes HTTP requests | Tests one Gate 403. All meaningful tests are `@pytest.mark.skip` |
| `test_loading_to_analysis.py` | Integration test filename | Entire file is `@pytest.mark.skip` |
| `test_load_combinations.py` | Title says "Load Combination Engine" | Tests a stub class defined in the test file, not `core.loading` |
| `test_slab_load_assembly.py` | Title says "Slab Load Assembly" | All three assembler classes are stubs defined in the test file |
| `test_matrix_stiffness_solver.py` | Title says "Matrix Stiffness Solver" | `MatrixStiffnessSolver` is a stub |
| `test_moment_coefficient_solver.py` | Title says "Moment Coefficient Solver" | `MomentCoefficientSolver` is a stub |
| `test_calc_trace_renderer.py` | Tests reporting renderer | Stub `CalcTraceRenderer`, not the real engine |

---

## Section D: Gaps by Priority

### Tier 1 — Critical (zero coverage, used in every project)

**1. Routers / API endpoints**
- 8 routers, ~50 endpoints, zero HTTP-level tests.
- No coverage of gate enforcement per-endpoint, async job creation, or error responses.

**2. Agent orchestration (LangGraph)**
- The entire user experience flows through `agents/graph.py`.
- No tests for state transitions, routing logic, gate decisions, or any individual agent node.

**3. Services layer**
- The bridge between routers and core logic.
- Failures here mean wrong results silently delivered to the client.
- Zero tests for any of the four services.

**4. Reporting layer**
- Generates client deliverables (PDF calc sheets, rebar schedules, quantity takeoffs).
- Any failure is a contract failure.
- Seven modules, zero tests.

### Tier 2 — High (partial coverage with known gaps)

**5. EC2 design** — Only beam tested. Columns, footings, walls, slabs — all zero.

**6. BS8110 design gaps** — Footing, wall, special slab, staircase — all zero.

**7. Storage / database** — Production uses SQLAlchemy + asyncpg + Alembic migrations. Tests use an in-memory Python dict. The two have never been tested against each other.

**8. Auth flows** — JWT token generation, 2FA, Google OAuth, and all `auth/router.py` flows untested at the HTTP level.

### Tier 3 — Medium

**9. Parsing layer (DXF/PDF)** — No isolated unit tests. Edge cases (malformed file, missing entities, wrong scale) are unexercised.

**10. Drawing generators** — Five of six member types have zero drawing tests.

**11. Real database integration** — No test spins up a real Postgres (even via Docker) to validate Alembic migrations, ORM queries, or asyncpg connectivity.

**12. Real LLM integration** — Only one test (`test_vision_agent.py`) calls Gemini. No tests verify the prompt/response contract for analyst, designer, or drafter agent prompts.

---

## Section E: Coverage Summary Table

| Layer | Modules | Tested | Not Tested | Approx. Coverage |
|---|---|---|---|---|
| Core analysis solvers | 8 | 7 | 1 | ~87% |
| Core design BS8110 | 8 | 4 (basic) | 4 | ~40% |
| Core design EC2 | 7 | 1 | 6 | ~17% |
| Core loading | 6 | Stubs only | 6 (real) | ~0% real |
| Core parsing | 2 | 0 | 2 | 0% |
| Core drawing | 6 | 1 | 5 | ~17% |
| Core reporting | 8 | 0 | 8 | 0% |
| Services | 4 | 0 | 4 | 0% |
| Routers | 8 | 0 | 8 | 0% |
| Agents | 8 | 0 | 8 | 0% |
| Auth | 5 | 1 (manager only) | 4 | ~20% |
| Storage / DB | 5 | 0 | 5 | 0% |

**Estimated missing tests: ~150 unit, ~30 integration, ~15 E2E.**

The three most urgent areas to address first are the **agents layer**, the **services layer**, and **real database connectivity** — because every other test gap builds on those foundations being known-good.
