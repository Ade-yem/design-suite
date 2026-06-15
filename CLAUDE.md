# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Design Suite is an AI-driven structural engineering IDE — a monorepo with a FastAPI backend (`apps/api`) and a Next.js frontend (`apps/web`). It automates the pipeline from architectural drawings (DXF/PDF) → geometry parsing → load analysis → reinforcement design → RC drawings, with human-in-the-loop safety gates at each phase.

## Development Setup

### Installing Git Hooks

After cloning the repository, install the pre-commit hook to ensure code quality before commits:

```bash
bash scripts/install-hooks.sh
```

This installs automated checks that run before every commit:
- **Backend**: pytest test suite + type checking
- **Frontend**: ESLint + TypeScript compilation

Checks are run only on changed files. To bypass checks (not recommended): `git commit --no-verify`

## Commands

### Backend (`apps/api/`)

```bash
# Run dev server (from apps/api/)
uvicorn main:app --reload --port 5000

# Run all tests (from apps/api/)
pytest

# Run a single test file
pytest tests/unit/analysis/test_something.py -v

# Run a specific test by name
pytest -k "test_function_name" -v

# Database migrations
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "description"

# Type checking
pyrefly check
```

### Frontend (`apps/web/`)

```bash
npm run dev      # Dev server with Turbopack
npm run build    # Production build
npm run lint     # ESLint
```

### Full Stack

```bash
docker-compose up -d   # Start PostgreSQL + API + Web
docker-compose down
```

API docs available at `http://localhost:5000/api/docs` when backend is running.

## Architecture

Always refer to the [pipeline architecture document](./guides/pipeline_architecture.md)

### LangGraph Agent Pipeline

The backbone is a `StateGraph` in `apps/api/agents/graph.py`. Every node reads from and writes partial updates to `StructuralDesignState` (`agents/state.py`) — this is the most important object in the system.

**Five agent nodes:**
1. `supervisor_node` — Routes to the correct agent based on `pipeline_status`
2. `parser_node` — Parses DXF/PDF files, extracts nodes/beams/columns
3. `analyst_node` — Runs 2D FEA, produces BMD/SFD diagrams
4. `designer_node` — Calculates reinforcement per BS8110 or Eurocode 2; may self-weight iterate up to 5 times
5. `drafter_node` — Converts design schedules to SVG drawing primitives

**Four hard-stop gates** (`agents/gates.py`) pause the graph and wait for HTTP confirmation before the next agent runs:
- Gate 1: Engineer confirms parsed geometry (file upload)
- Gate 2: Engineer confirms factored load combinations
- Gate 3: Engineer confirms reinforcement schedule before drafting
- Gate 4: Engineer finalises drawing set

Resumption happens via `POST /api/v1/pipeline/{project_id}/resume`.

### State Convention

`StructuralDesignState` uses `Annotated[list, add]` for `messages` and `agent_logs` — LangGraph **appends** to these rather than replacing. All other fields are plain Python; nodes overwrite them. Use `is None` checks for routing logic, not sentinel strings.

**Units (enforced globally):** forces in kN, moments in kNm, lengths in m (section dimensions are mm), stresses in MPa, areas in mm².

### API Layer

All domain endpoints are under `/api/v1/`. Routers live in `apps/api/routers/` and are registered in `main.py` (which contains no business logic). Auth endpoints (`fastapi-users`) mount under `/api/auth/` (`/jwt`, register, reset, verify, `/google`) and `/api/users/`.

The layering is: **router → service → core module**. Core modules under `apps/api/core/` implement the structural engineering calculations; services in `apps/api/services/` orchestrate them; routers only handle HTTP concerns.

| Area | Router | Core / Storage |
|------|--------|------|
| File parsing | `routers/files.py` | `core/parsing/`, `services/files.py` |
| Load combinations | `routers/loading.py` | `core/loading/`, `services/loading.py` |
| FEA | `routers/analysis.py` | `core/analysis/` |
| Reinforcement design | `routers/design.py` | `core/design/` |
| Drawing output | `routers/drawings.py` | `core/drawing/` |
| Calculation reports | `routers/reports.py` | `core/reporting/` |
| Gate snapshots (artifacts) | `routers/artifacts.py` | `storage/artifact_store.py` |
| Async jobs | `routers/jobs.py` | `storage/job_store.py` |
| Projects | `routers/projects.py` | `storage/project_store.py` |
| Greeting / onboarding | `routers/greeting.py` | — |

WebSocket endpoints in `apps/api/websocket.py` stream live agent logs (`/ws/pipeline`) and chat (`/ws/chat`).

### Pluggable Storage Layer

`apps/api/storage/` holds swappable store singletons. Each exposes a **single public interface** with both a memory and a persistent backend, chosen by a `make_*()` factory at import time based on `settings`:

| Store | Memory backend | Persistent backend | Selector |
|-------|----------------|--------------------|----------|
| `project_store` | `MemoryProjectStore` | `PostgresProjectStore` | `PROJECT_STORE_BACKEND` (`memory` \| `postgres`) |
| `artifact_store` | `MemoryArtifactStore` | `PostgresArtifactStore` | follows `PROJECT_STORE_BACKEND` |
| `job_store` | `MemoryJobStore` | `RedisJobStore` | `JOB_STORE_BACKEND` (auto-promoted to `redis` when `REDIS_URL` is set) |
| `file_handler` / `file_backends/` | local disk | Cloudinary | `FILE_STORAGE_BACKEND` (`local` \| `cloudinary`) |

`services/files.py` additionally owns a module-level `_GeometryStore` singleton (`file_service._store`) caching parsed geometry and scale per project.

**Convention:** all store backends default to in-memory so the app (and tests) run with no database or external services. `PROJECT_STORE_BACKEND` defaults to `"memory"` when unset.

### Artifacts (gate snapshots)

When a safety gate is approved, an immutable **artifact** is frozen into `artifact_store` with stage, status (`signed_off`), author, and timestamp — the project's audit trail. Gate 1 (`PUT /api/v1/files/{project_id}/verify`) snapshots the verified geometry. Retrieval is via `GET /api/v1/artifacts/{project_id}` (list) and `GET /api/v1/artifacts/detail/{artifact_id}` (full content). Domain model: `schemas/artifact.py:ArtifactRecord`; ORM: `db/models/artifact.py:Artifact` (with `ArtifactStage` enum). The frontend mirrors this in `src/stores/artifactStore.ts` (`ArtifactsDrawer`).

### Frontend

The UI is a Next.js App Router app. The main layout is:

```
AuthGuard → AppHeader (+ StageTracker) → CanvasViewport + ChatSidebar
```

- **CanvasViewport** — SVG canvas rendering geometry/reinforcement; file upload zone
- **ChatSidebar** — Agent message stream; currently uses mock timeouts, WebSocket integration is pending
- **StageTracker** — Visual pipeline progress indicator (parsing → verification → analysis → drafting)

Global auth state lives in `src/stores/authStore.ts` (Zustand). The API client is at `src/lib/api.ts` — an Axios instance with a JWT token interceptor.

### Database

SQLAlchemy 2.0 async ORM models live in `apps/api/db/models/`: `User`, `Project` (+ `ProjectMember`, `ProjectGeometry`, `ProjectLoad`, `ProjectAnalysis`, `ProjectDesign`, `ProjectDrawing` in `project.py`), `Artifact`, `Organisation`, OAuth accounts, and `pipeline.py`. `db/base.py` holds the declarative `Base`; `db/session.py` lazily builds the async engine and raises `RuntimeError: DATABASE_URL is not set` if a Postgres-backed path is hit without a DSN. Alembic migrations are in `apps/api/migrations/` (config: `apps/api/alembic.ini`).

Note: `apps/api/models/` is a **separate** package holding design-code calculation logic and schemas (`models/bs8110/`, `models/ec2/`, `models/loading/`, `models/analysis/`) — not the persistence ORM. Request/response domain models are Pydantic schemas in `apps/api/schemas/`.

### Testing Layout

```
apps/api/tests/
├── unit/          # Fast isolated tests (analysis, design, loading, storage, etc.)
├── integration/   # API + pipeline tests (agents/, api/, pipeline/)
├── e2e/           # End-to-end pipeline stubs (mostly skipped)
├── beam_8110/, slab/, benchmarks/  # Calc-specific suites
└── test_*.py      # Standalone test files for auth, column/slab design
```

`pytest.ini` sets `asyncio_mode = auto`, so async test functions work without extra decorators.

**Test isolation (`tests/conftest.py`):**
- Forces `PROJECT_STORE_BACKEND=memory` and sets dummy `GEMINI_API_KEY`/`GOOGLE_API_KEY` at import so nothing hits a database or the network.
- An autouse `clear_stores` fixture resets `project_store`, `artifact_store`, `file_service._store`, and `job_store` before every test.
- An autouse `mock_llm_calls` fixture patches the lazy `_get_llm()` seams in `agents.parser`, `agents.analyst`, and `agents.designer` to return canned responses. **All three agents construct their LLM lazily via `_get_llm()`** — never at module import — so the package imports without an API key.
- `authenticated_client` / `authenticated_user` fixtures override the `current_active_user` dependency for API tests that need auth (no token/DB required).
- Vision/parser integration tests read sample drawings from the repo-root `sample/` folder (`Floor-beam.dxf` / `.pdf`); they skip when the files are absent.

## Key Development Notes

- **Stage-gate sequencing is enforced:** calling a downstream endpoint (e.g., analysis) before confirming the upstream gate (geometry) will return an error. Gate dependencies live in `dependencies.py` (`require_geometry_verified`, etc.) and are applied at the router level via `Depends()` — never embedded in handler bodies. Gate confirmation is the only way to unlock the next phase.
- **Designer self-weight loop:** the `designer_node` iterates self-weight recalculation until convergence or 5 iterations — design changes that affect member sizes can trigger this.
- **DXF/PDF input units are mm:** the parser normalises to meters before writing to state. Do not assume raw file coordinates are already in SI.
- **`main.py` stays logic-free:** it is the wiring layer only. Business logic belongs in `core/`, orchestration in `agents/`.
- **LLM construction is lazy:** every agent that calls Gemini exposes a `_get_llm()` function and calls it at use-time — never instantiate `ChatGoogleGenerativeAI` at module scope (it would require an API key at import and break test collection).
- **Stores default to memory:** the app boots with no database, Redis, or cloud file storage. Reach for the persistent backends only by setting the relevant env var (`DATABASE_URL`, `REDIS_URL`, Cloudinary creds).
