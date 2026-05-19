# Project Audit — Design Suite

**Date:** 2026-05-18  
**Audited by:** Senior QA + Fullstack Review  
**Scope:** Full monorepo — `apps/api` (FastAPI) and `apps/web` (Next.js)

---

## Backend (`apps/api`) — What's Done

### Core Engineering (Production-Grade)

All structural engineering logic is real and complete:

| Module | Status |
|---|---|
| `core/analysis/` — beam, column, slab, footing, staircase, wall solvers | Real |
| `core/design/rc/bs8110/` — full BS8110-1:1997 design suite | Real |
| `core/design/rc/eurocode2/` — parallel EC2 suite | Real |
| `core/design/rc/common/` — bar selection, interaction diagrams | Real |
| `core/loading/` — ULS/SLS factored combinations, assemblers | Real |
| `core/parsing/` — DXF (`ezdxf`) and PDF parsing | Real |
| `core/drawing/` — drawing command generation for all member types | Real |
| `core/reporting/` — calc sheets, PDF export, rebar schedules, quantities | Real |

### LangGraph Agent Pipeline

The full 9-node pipeline compiles and runs correctly (after `.env` is loaded):

```
supervisor → parser → [Gate 1] → analyst → [Gate 2] → designer → [Gate 3] → drafter → [Gate 4]
```

All agents (`parser`, `analyst`, `designer`, `drafter`) are real — they call the Gemini LLM for extraction/interpretation and call the engineering core modules for computation. The 4 human-in-the-loop gates enforce stage ordering correctly.

### API Layer

All 10 routers are registered in `main.py` and import cleanly:

- `projects`, `files`, `loading`, `analysis`, `design`, `drawings`, `reports`, `pipeline`, `jobs`, `chat`
- Auth: JWT login, register, email verify, password reset, Google OAuth, 2FA — all real.

### Services Layer

All 4 services (`FileService`, `LoadingService`, `AnalysisService`, `DesignService`) are wired correctly — router → service → core module. Async wrappers run CPU-bound work in thread pools.

### WebSocket

`/ws/{project_id}` is a real implementation. It streams `astream_events` from the LangGraph graph and sends typed messages back to the client:
- `agent_message` — streamed LLM output chunks
- `status_log` — tool completion events
- `gate_reached` — human confirmation required
- `drawing_commands` — generated drawing primitives

---

## Backend — Gaps and Problems

**Fix:** swap those two lines. Rotate the exposed key immediately.

### 2. `.env` Typo — Google OAuth potentially broken

In `.env`, the key is `GOOGLE_CLIENT_SECRET` (misspelled). If `auth/router.py` reads `GOOGLE_CLIENT_SECRET` (correct spelling), Google OAuth sign-in silently fails. Verify the key name used in code.

### 3. In-Memory Stores — Data Lost on Restart

All pipeline data lives in Python dicts in-process. Four stores have no persistence:

| Store | Location | Data at risk |
|---|---|---|
| `_GeometryStore` | `services/files.py` | Parsed DXF/PDF geometry |
| `_LoadingStore` | `services/loading.py` | Load definitions and outputs |
| `_AnalysisStore` | `services/analysis.py` | Analysis results |
| `_DesignStore` | `services/design.py` | Reinforcement design results |

The database ORM models for pipeline data (`StructuralMember`, `LoadCase`, `LoadCombination`, `AnalysisResult`, `DesignResult`, `DrawingCommand`) mentioned in `CLAUDE.md` **do not exist** in `db/models/`. Currently only 4 ORM models exist: `User`, `Organisation`, `OAuthAccount`, `Project`. Alembic migrations only cover those.

### 4. WebSocket Reinitializes Pipeline on Every Connection

`websocket.py:39` always passes `"pipeline_status": "created"` regardless of actual project state. Reconnecting a browser window resets the pipeline instead of resuming at the current gate.

```python
# Current (broken for resumption):
{"messages": [...], "project_id": project_id, "pipeline_status": "created"}

# Should be:
{"messages": [...], "project_id": project_id, "pipeline_status": project_store.get_status(project_id)}
```

### 5. `routers/chat.py` — Orphaned / Broken Router

Uses the old LangGraph invoke pattern (`agent_app.invoke()`) and references `result["messages"][0].text` (wrong attribute — should be `.content`). Does not use the current project-based pipeline flow. Should be removed or rewritten around the WebSocket + pipeline architecture.

### 6. `core/analysis/global_solver.py` — Stub

Global frame analysis (multi-storey frame, lateral loads) is not implemented. Not blocking for single-member analysis scope.

### 7. `core/design/steel/` — Empty

Steel design directory exists but has no implementation. Not blocking if only RC design is in scope.

---

## Frontend (`apps/web`) — What's Done

| Area | Status |
|---|---|
| Login — email/password + 2FA OTP flow | Real, fully wired to backend |
| Register + email verification + resend | Real, fully wired |
| Forgot password + reset password via token | Real, fully wired |
| Google OAuth flow | Real (depends on backend OAuth config) |
| Zustand auth store + localStorage persistence | Real |
| Axios API client with JWT interceptor + 401 auto-logout | Real |
| Route protection via `AuthGuard` | Real |
| Radix UI component library (60+ primitives) | Real |

---

## Frontend — What's Stubbed

Everything beyond the auth flow is a UI shell with no backend connection.

### `CanvasViewport` — Zero real functionality

- File drag-and-drop sets a boolean flag only — no upload to `/api/v1/files/upload/{project_id}`
- Always renders a hardcoded SVG demo ("AI Parsing Complete · 14 members detected")
- Toolbar buttons (Select, Pan, Zoom, Fit) do nothing
- No DXF rendering engine, no geometry display from real parsed data

### `ChatSidebar` — Mock only

- Sends no HTTP requests, opens no WebSocket
- `setTimeout(1500ms)` fakes a bot reply with a placeholder string
- No connection to the backend `/ws/{project_id}` WebSocket

### Main Workspace (`page.tsx`)

- `currentStage` hardcoded to `"parsing"` — never changes
- No project ID management — no call to create or fetch a project
- `StageTracker` is visual-only, not subscribed to any backend state

### No WebSocket client anywhere in the frontend

Zero `WebSocket`, `ws://`, or `wss://` references exist in `apps/web/src/`. The backend WebSocket endpoint has no consumer on the frontend.

---

## Integration Map — Connected vs. Disconnected

```
Frontend                        Backend
────────────────────────────────────────────────────────────────
Auth pages       ──── HTTP ────► /auth/*, /users/me         ✅

CanvasViewport   ────── ✗ ─────  /api/v1/files/upload
                 ────── ✗ ─────  /api/v1/pipeline/{id}/run
ChatSidebar      ────── ✗ ─────  /ws/{project_id}
StageTracker     ────── ✗ ─────  /api/v1/projects/{id}
Gate approval    ────── ✗ ─────  /api/v1/pipeline/{id}/resume
Drawing canvas   ────── ✗ ─────  /api/v1/drawings/{id}
Reports          ────── ✗ ─────  /api/v1/reports/
```

---

## Priority Gap List — What Needs to Be Done

Ordered by dependency — each item unblocks the next.

### P0 — Fix Now (blocking or security)

1. **Fix hardcoded Gemini API key** in `agents/parser.py:43` — swap commented line back, rotate the exposed key.
2. **Verify `GOOGLE_CLIENT_SECRET` typo** in `.env` — check what field name `auth/router.py` actually reads.
3. **Fix WebSocket pipeline_status** in `websocket.py:39` — load real project status from `project_store` before starting the graph stream.

### P1 — Core Frontend-Backend Integration

4. **Project management UI** — project creation form, project listing page, persist `project_id` in global state (Zustand). Every subsequent API call depends on a real `project_id`.
5. **File upload** — wire `CanvasViewport` drag-and-drop to `POST /api/v1/files/upload/{project_id}`, poll job status via `GET /api/v1/jobs/{job_id}`, then render parsed geometry from the response.
6. **WebSocket client hook** — add a `useProjectSocket(projectId)` hook that connects to `/ws/{project_id}` and dispatches typed messages:
   - `agent_message` → append to chat panel
   - `gate_reached` → update stage tracker, show confirmation button
   - `drawing_commands` → push to canvas renderer
7. **ChatSidebar** — replace `setTimeout` mock with the WebSocket hook.
8. **StageTracker** — subscribe to `gate_reached` events; fetch project status from `GET /api/v1/projects/{id}` on mount.
9. **Gate confirmation UI** — after `gate_reached`, show an "Approve" button that calls `POST /api/v1/pipeline/{id}/resume`.

### P2 — Database Persistence

10. **Add ORM models** for `StructuralMember`, `LoadCase`, `AnalysisResult`, `DesignResult`, `DrawingCommand` in `db/models/`.
11. **Alembic migration** for those new models.
12. **Migrate the 4 in-memory service stores** to read/write the new database tables so pipeline data survives server restarts.

### P3 — Cleanup and Polish

13. **Remove or rewrite `routers/chat.py`** — currently broken and architecturally inconsistent.
14. **Wire `CanvasViewport`** to render real drawing commands from `GET /api/v1/drawings/{project_id}`.
15. **Add frontend error handling** for gate sequencing errors (backend already returns `409` errors for out-of-order calls; frontend needs to surface them).

---

## Summary

The **backend engineering core** (solvers, design modules, loading, parsing, reporting) and the **LangGraph agent pipeline** are substantially complete and real. The **auth system** is production-ready end-to-end on both frontend and backend.

The main gap is **frontend-backend integration for the design workflow** — canvas, chat, stage tracking, and pipeline controls are all UI shells that need to be wired to the already-working backend APIs and WebSocket.

The secondary gap is **database persistence** for pipeline data. All geometry, loads, analysis, and design results currently live in-memory and are lost on server restart. The ORM models and migrations for this data do not yet exist.
