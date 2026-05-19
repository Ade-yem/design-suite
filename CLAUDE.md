# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Design Suite is an AI-driven structural engineering IDE — a monorepo with a FastAPI backend (`apps/api`) and a Next.js frontend (`apps/web`). It automates the pipeline from architectural drawings (DXF/PDF) → geometry parsing → load analysis → reinforcement design → RC drawings, with human-in-the-loop safety gates at each phase.

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

All domain endpoints are under `/api/v1/`. Routers live in `apps/api/routers/` and are registered in `main.py` (which contains no business logic). Auth endpoints (`fastapi-users`) mount at `/auth/` and `/users/`.

The layering is: **router → service → core module**. Core modules under `apps/api/core/` implement the structural engineering calculations; services in `apps/api/core/` (and domain subfolders) orchestrate them; routers only handle HTTP concerns.

| Area | Router | Core |
|------|--------|------|
| File parsing | `routers/files.py` | `core/parsing/` |
| Load combinations | `routers/loading.py` | `core/loading/` |
| FEA | `routers/analysis.py` | `core/analysis/` |
| Reinforcement design | `routers/design.py` | `core/design/` |
| Drawing output | `routers/drawings.py` | `core/drawing/` |
| Calculation reports | `routers/reports.py` | `core/reporting/` |

WebSocket endpoints in `apps/api/websocket.py` stream live agent logs (`/ws/pipeline`) and chat (`/ws/chat`).

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

SQLAlchemy 2.0 async models in `apps/api/models/`. Alembic migrations in `apps/api/migrations/`. Key models: `User`, `Project`, `StructuralMember`, `LoadCase`, `LoadCombination`, `AnalysisResult`, `DesignResult`, `DrawingCommand`. Design-code-specific logic is split into `models/bs8110/` and `models/ec2/`.

### Testing Layout

```
apps/api/tests/
├── unit/          # Fast isolated tests (analysis, design, loading, etc.)
├── integration/   # Tests hitting the real database
├── e2e/           # End-to-end pipeline tests
└── test_*.py      # Standalone test files for auth, column/slab design
```

`pytest.ini` sets `asyncio_mode = auto`, so async test functions work without extra decorators.

## Key Development Notes

- **Stage-gate sequencing is enforced:** calling a downstream endpoint (e.g., analysis) before confirming the upstream gate (geometry) will return an error. Gate confirmation is the only way to unlock the next phase.
- **Designer self-weight loop:** the `designer_node` iterates self-weight recalculation until convergence or 5 iterations — design changes that affect member sizes can trigger this.
- **DXF/PDF input units are mm:** the parser normalises to meters before writing to state. Do not assume raw file coordinates are already in SI.
- **`main.py` stays logic-free:** it is the wiring layer only. Business logic belongs in `core/`, orchestration in `agents/`.
