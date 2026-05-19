# Remediation Plan — Design Suite

**Date:** 2026-05-19
**Based on:** `project_audit.md` + `test_suite_audit.md`
**Scope:** Full monorepo — `apps/api` (FastAPI) and `apps/web` (Next.js)

---

## Dependency Order

```
Phase 0 (security fixes)
    │
    ▼
Phase 1 (DB persistence)  ──────────────────────────►  Phase 3 (test foundation)
    │                                                         │
    ▼                                                         ▼
Phase 2.1 (project mgmt UI)                           Phase 3.1 (fix stubs)
    │                                                         │
    ▼                                                         ▼
Phase 2.2 (file upload)                               Phase 3.3 (un-skip integration)
    │                                                         │
    ▼                                                         ▼
Phase 2.3 (WebSocket hook)                            Phase 4 (coverage tiers 1→2→3)
    │
    ▼
Phase 2.4–2.6 (chat, stage, gates)
    │
    ▼
Phase 5 (cleanup)
```

Phase 0 is the only true blocker for everything else. Phase 1 (DB) and Phase 3 (test foundation) can be worked in parallel once Phase 0 is done. Phase 2 (frontend integration) depends on Phase 1 completing so real `project_id`s and persisted data are available.

---

## Phase 0 — Security & Critical Fixes

**Estimated effort: 1–2 hours. Must be done before anything else.**

### 0.1 — Verify and fix the Gemini key exposure

The audit flagged `agents/parser.py:43`. Current code correctly reads `settings.GEMINI_API_KEY`. Verify git history to confirm a raw key was never committed:

```bash
git log -p apps/api/agents/parser.py | grep -A2 -B2 "AIza"
```

If a raw key ever appeared in any commit, rotate it immediately in Google AI Studio — exposure is permanent once pushed regardless of whether it was later removed.

### 0.2 — Verify the `.env` GOOGLE_CLIENT_SECRET spelling

`config.py:115` reads `GOOGLE_CLIENT_SECRET` (correct). Check the `.env` file for a misspelling such as `GOOGLE_CLIENT_SECERT`. If the `.env` key name differs from what config reads, Google OAuth silently receives an empty string and all OAuth sign-ins fail without an explicit error message.

### 0.3 — Fix WebSocket pipeline resumption

`websocket.py:39` always passes `"pipeline_status": "created"`, which resets the pipeline on every browser reconnect. Read the real project status from `project_store` before invoking the graph stream.

```python
# Current (broken for resumption):
{"messages": [...], "project_id": project_id, "pipeline_status": "created"}

# Fix — load real status first:
status = project_store.get_status(project_id)
{"messages": [...], "project_id": project_id, "pipeline_status": status}
```

---

## Phase 1 — Database Persistence

**Estimated effort: 1–2 days. Unblocks integration tests and prevents data loss on restart.**

`db/models/` currently has only 4 ORM models: `User`, `Organisation`, `OAuthAccount`, `Project`. Six models referenced in CLAUDE.md do not exist. All pipeline data lives in Python dicts in-process and is lost on every server restart.

### 1.1 — Add missing ORM models

Create the following files in `db/models/`:

| New file | Model(s) | Key fields |
|---|---|---|
| `structural_member.py` | `StructuralMember` | `project_id`, `member_type`, `geometry_json`, `gate1_confirmed` |
| `load_case.py` | `LoadCase`, `LoadCombination` | `member_id`, `loads_json`, `combinations_json`, `gate2_confirmed` |
| `analysis_result.py` | `AnalysisResult` | `member_id`, `bmd_json`, `sfd_json`, `reactions_json` |
| `design_result.py` | `DesignResult` | `member_id`, `design_code`, `schedule_json`, `gate3_confirmed` |
| `drawing_command.py` | `DrawingCommand` | `project_id`, `member_id`, `commands_json`, `gate4_confirmed` |

Each model subclasses `db.base.Base` and includes `created_at` / `updated_at` timestamp columns.

### 1.2 — Alembic migration

Register the new models in `migrations/env.py`, then generate and apply the migration:

```bash
alembic revision --autogenerate -m "add pipeline data models"
# Review the generated file in migrations/versions/ before applying
alembic upgrade head
```

Verify foreign key constraints and indexes in the generated migration before applying to any shared environment.

### 1.3 — Migrate the four in-memory service stores to DB

Each service currently uses a Python dict. Replace each with async SQLAlchemy reads/writes using the new models:

| Service | Current store | Target model |
|---|---|---|
| `services/files.py` | `_GeometryStore` | `StructuralMember` |
| `services/loading.py` | `_LoadingStore` | `LoadCase` + `LoadCombination` |
| `services/analysis.py` | `_AnalysisStore` | `AnalysisResult` |
| `services/design.py` | `_DesignStore` | `DesignResult` |

Services already receive a DB session via `Depends(get_async_session)`. Thread-pool wrappers for CPU-bound core calls stay in place; dict mutations become `db.add()` / `await db.commit()` calls.

---

## Phase 2 — Frontend-Backend Integration

**Estimated effort: 3–5 days. Items are ordered by dependency — each unblocks the next.**

### 2.1 — Project management UI *(blocks all other frontend work)*

- Create `src/app/dashboard/page.tsx`: list existing projects via `GET /api/v1/projects/`, add a "New Project" button that calls `POST /api/v1/projects/`.
- Add `projectId` to the Zustand store (`src/stores/authStore.ts` or a dedicated `projectStore.ts`).
- The main workspace `page.tsx` must read `projectId` from the store. Without a real `project_id`, no subsequent API call is possible.

### 2.2 — File upload wiring in CanvasViewport

- Replace the boolean flag on drag-and-drop with a call to `POST /api/v1/files/upload/{project_id}`.
- Poll job status via `GET /api/v1/jobs/{job_id}` until the job completes.
- On completion, fetch parsed geometry from the response and render it on the SVG canvas. Remove the hardcoded demo SVG ("AI Parsing Complete · 14 members detected").

### 2.3 — WebSocket client hook

Create `src/hooks/useProjectSocket.ts`:

- Connect to `ws://host/ws/{project_id}` on mount, disconnect on unmount.
- Parse and dispatch typed messages:
  - `agent_message` → chat panel
  - `status_log` → pipeline log
  - `gate_reached` → stage tracker + confirmation UI
  - `drawing_commands` → canvas renderer
- Handle reconnection with exponential backoff.

This hook is consumed by components in 2.4–2.6.

### 2.4 — Wire ChatSidebar to the WebSocket

Replace the `setTimeout(1500ms)` mock in `ChatSidebar` with `useProjectSocket`. `agent_message` events append to the chat panel. User messages sent from the chat input are POSTed through the appropriate pipeline endpoint.

### 2.5 — Wire StageTracker to real pipeline state

- On mount, fetch project status from `GET /api/v1/projects/{project_id}` to show the correct current stage.
- Subscribe to `gate_reached` events from `useProjectSocket` to advance the tracker in real time.
- `currentStage` in `page.tsx` must be driven by this state — remove the hardcoded `"parsing"` value.

### 2.6 — Gate confirmation UI

When a `gate_reached` event arrives, render an "Approve" button in the relevant stage panel. Clicking it calls `POST /api/v1/pipeline/{project_id}/resume`. Disable the button and show a spinner while the request is in flight. The backend already returns `409 Conflict` for out-of-order calls — display that error inline rather than letting it fail silently.

---

## Phase 3 — Test Suite: Fix Structural Problems

**Estimated effort: 2 days. These are test-correctness issues that create false confidence.**

### 3.1 — Delete or rewrite the six stub-based tests

The following test files define fake classes inside the test file instead of importing the real module. They provide zero real coverage:

| File | Fake class | Real module to import instead |
|---|---|---|
| `tests/unit/loading/test_load_combinations.py` | `LoadCombinationEngine` (stub) | `core.loading.load_combinations.LoadCombinationEngine` |
| `tests/unit/loading/test_slab_load_assembly.py` | 3 assembler stubs | `core.loading.slab_load_assembly` |
| `tests/unit/analysis/test_matrix_stiffness_solver.py` | `MatrixStiffnessSolver` (stub) | `core.analysis.global_solver` |
| `tests/unit/analysis/test_moment_coefficient_solver.py` | `MomentCoefficientSolver` (stub) | `core.analysis.beam_solver` or equivalent |
| `tests/unit/reporting/test_calc_trace_renderer.py` | `CalcTraceRenderer` (stub) | `core.reporting.calc_sheet` |

For each: import the real class, port the existing test cases, and delete the stub definition.

### 3.2 — Fix conftest.py to use a real test database

The `async_client` fixture hits the live app wired to a Python dict, not Postgres. Replace it with a test-scoped async PostgreSQL database. Add a `DATABASE_URL` for tests in `pytest.ini` or a `.env.test`. This is the prerequisite for all integration tests in Phase 4.

Options:
- Local Postgres with a dedicated test DB (simplest)
- Docker Compose test service (`docker-compose -f docker-compose.test.yml up -d`)
- `pytest-docker` plugin for fully isolated per-run DBs

### 3.3 — Un-skip and implement existing integration tests

- `tests/integration/test_loading_router.py` — implement the skipped endpoint tests using the real DB client from 3.2.
- `tests/integration/test_loading_to_analysis.py` — implement the three skipped test methods.

---

## Phase 4 — Test Suite: Coverage Expansion

**Estimated effort: 4–6 days. Work through tiers in order.**

### Tier 1 — Services layer *(four modules, zero tests)*

Write unit tests for each service using `AsyncMock` for DB sessions and core module calls:

- `services/files.py` — parse job creation, scale detection, geometry storage.
- `services/loading.py` — ULS/SLS combination sequencing and result storage.
- `services/analysis.py` — member analysis orchestration and result storage.
- `services/design.py` — design override handling and result storage.

### Tier 1 — Agent orchestration *(eight modules, zero tests)*

Use `unittest.mock.patch` to stub LLM calls and test graph logic without hitting Gemini:

- `agents/graph.py` — state transitions through the full pipeline (supervisor routing, each gate pause and resume).
- `agents/gates.py` — all four gate conditions: correct pass, wrong-order fail, missing-data fail.
- `agents/designer.py` — self-weight iteration loop (convergence case and 5-iteration cap).
- Individual agent nodes — verify each node reads correct state fields and writes expected partial updates.

### Tier 1 — Auth HTTP flows *(router untested at HTTP level)*

Add tests in `tests/auth/` using the `async_client` fixture:

- `POST /auth/login` — valid credentials, wrong password, unverified email, 2FA required.
- `POST /auth/register` — success, duplicate email, weak password.
- `GET /auth/verify-email` — valid token, expired token.
- `POST /auth/forgot-password` and `POST /auth/reset-password`.
- Google OAuth callback — mock `httpx` calls to Google's token endpoint.

### Tier 2 — EC2 design gaps

Add test files for each untested EC2 module:

- `tests/unit/design/test_ec2_column.py`
- `tests/unit/design/test_ec2_footing.py`
- `tests/unit/design/test_ec2_slab.py`
- `tests/unit/design/test_ec2_wall.py`
- `tests/unit/design/test_ec2_staircase.py`

### Tier 2 — BS8110 gaps

- `tests/unit/design/test_bs8110_footing.py`
- `tests/unit/design/test_bs8110_wall.py`
- `tests/unit/design/test_bs8110_staircase.py`
- `tests/unit/design/test_bs8110_special_slab.py`
- `tests/unit/design/test_select_reinforcement.py`
- `tests/unit/design/test_interaction_diagram.py`

Use hand-calculated reference values where available. Several benchmarks are already written in comments inside `tests/e2e/test_full_pipeline_bs8110.py`.

### Tier 2 — Reporting layer *(seven modules, zero tests)*

Add tests for each reporting module. For `PDFExportEngine` (WeasyPrint), assert a non-empty PDF bytestring is returned rather than testing exact byte content. For `TemplateRenderer` (Jinja2), assert expected HTML substrings appear in the output.

Modules to cover:
`CalcSheetEngine`, `BMDGenerator`, `SFDGenerator`, `RebarScheduleEngine`, `MaterialQuantityEngine`, `ComplianceReportEngine`, `PDFExportEngine`, `TemplateRenderer`, `InputNormalizer`

### Tier 2 — Drawing generators *(five of six member types untested)*

Mirror the structure of `tests/unit/drafting/test_beam_drawing_generator.py` for each remaining generator:
- `ColumnDrawingGenerator`
- `SlabDrawingGenerator`
- `FootingDrawingGenerator`
- `WallDrawingGenerator`
- `StaircaseDrawingGenerator`

Test: bar positioning, cover bounds, scale consistency.

### Tier 3 — Un-skip E2E tests

`tests/e2e/test_full_pipeline_bs8110.py` has hand-calc benchmark values written in comments. Implement each test using the real test-DB client, running the full pipeline against a seeded project.

Mark any test that requires a live Gemini call with `@pytest.mark.integration` so it can be excluded from the fast local CI run:

```ini
# pytest.ini
markers =
    integration: requires live external services (Gemini, Cloudinary)
```

Run fast tests only:
```bash
pytest -m "not integration"
```

---

## Phase 5 — Cleanup & Polish

**Estimated effort: half a day.**

### 5.1 — Remove `routers/chat.py`

This router uses the old `agent_app.invoke()` pattern, references `.text` instead of `.content` on message objects, and is architecturally incompatible with the current WebSocket pipeline. The real chat path goes through the WebSocket. Remove the router registration from `main.py` and delete the file.

### 5.2 — Wire CanvasViewport to `GET /api/v1/drawings/{project_id}`

After Phase 1 persists `DrawingCommand` to the DB, fetch and render real drawing commands from the endpoint. Replace the static hardcoded SVG entirely. The toolbar buttons (Select, Pan, Zoom, Fit) should operate on this rendered geometry.

### 5.3 — Frontend error handling for gate sequences

The backend returns `409 Conflict` when a request arrives out of gate order. Add handling in `src/lib/api.ts` (Axios interceptor or per-call handler) that converts 409 responses into inline stage-panel error messages ("Analysis cannot start until geometry is confirmed") rather than a generic toast or silent failure.

---

## Coverage Targets by Phase

| Layer | Current | After Phase 3 | After Phase 4 |
|---|---|---|---|
| Core analysis solvers | ~87% | ~87% | ~95% |
| Core design BS8110 | ~40% | ~40% | ~90% |
| Core design EC2 | ~17% | ~17% | ~85% |
| Core loading | ~0% real | ~60% | ~90% |
| Core reporting | 0% | 0% | ~80% |
| Services | 0% | ~70% | ~90% |
| Routers | 0% | ~40% | ~80% |
| Agents | 0% | ~60% | ~85% |
| Auth | ~20% | ~80% | ~90% |
| Storage / DB | 0% | ~50% | ~75% |
