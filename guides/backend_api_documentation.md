# Structural Design Copilot - Backend API Documentation

Welcome to the Structural Design Copilot Backend API documentation. This API powers the AI-driven multi-agent structural engineering backend, facilitating the transition from architectural drawings to structural details.

## Base URL
All API endpoints (unless otherwise specified) are prefixed with:
`/api/v1`

## Authentication & Tenancy
The API uses **JWT-based authentication** (via `fastapi-users`).
- **Tenancy**: Every project and user belongs to an `Organisation`.
- **Isolation**: Users can only see and interact with projects belonging to their organization.
- **Authorization**: Bearer token required in the header: `Authorization: Bearer <token>`

---

## 1. Authentication & Users (`/api/auth`, `/api/users`)
Powered by `fastapi-users`. Login is **email-verified** and gated by a one-time
**2FA OTP**; **Google OAuth** is also supported.

- `POST /api/auth/register` — Register a new user (auto-creates the org).
- `POST /api/auth/jwt/login` — Login (`username`=email + `password`, form-data);
  may return a 2FA challenge requiring OTP verification before a JWT is issued.
- `POST /api/auth/jwt/logout` — Revoke the current JWT token.
- `POST /api/auth/request-verify-token` / `POST /api/auth/verify` — Email verification.
- `POST /api/auth/forgot-password` / `POST /api/auth/reset-password` — Password reset.
- `GET /api/auth/google/authorize` / `GET /api/auth/google/callback` — Google OAuth.
- `GET` / `PATCH /api/users/me` — Read / update the current user profile.

> Note: auth endpoints mount under `/api/auth` and `/api/users` (not `/api/v1`).

---

## 2. Projects (`/projects`)
Manages the top-level project entities. No gate restrictions apply here.

- `POST /projects/`
  - **Description**: Create a new project.
  - **Payload**: `{ "name": "...", "reference": "...", "client": "...", "design_code": "..." }`
- `GET /projects/`
  - **Description**: List all projects for the user's organisation.
- `GET /projects/{project_id}`
  - **Description**: Get full project details.
- `PUT /projects/{project_id}`
  - **Description**: Update project metadata.
- `DELETE /projects/{project_id}`
  - **Description**: Delete a project and all associated data.
- `GET /projects/{project_id}/status`
  - **Description**: Return pipeline stage completion status and next action.

---

## 3. Files & Parsing (`/files`)
Handles DXF/PDF uploads and geometry parsing (The "Vision Agent").
**Note**: Supports Local Storage (Dev) and Cloudinary (Prod).

- `POST /files/upload/{project_id}`
  - **Description**: Upload DXF/PDF and trigger async parsing.
  - **Payload**: `multipart/form-data` with `file`.
  - **Returns**: `{ "job_id": "...", "status_url": "..." }`
- `GET /files/{project_id}/parse-status/{job_id}`
  - **Description**: Poll async parsing job status.
- `GET /files/{project_id}/parsed`
  - **Description**: Get parsed structural JSON geometry. Requires `FILE_UPLOADED`.
- `GET` / `PUT /files/{project_id}/scale`
  - **Description**: Read / confirm the drawing scale (unit) factor before verification.
  - **Payload**: `{ "scale_factor": 0.001, "unit_label": "mm", "confirmed": true }`
- `PUT /files/{project_id}/storeys`
  - **Description**: Set the building storey count/height and extrapolate the typical
    floor into the multi-storey model **before Gate 1** (keeps the verification
    snapshot consistent with the working geometry). Idempotent.
  - **Payload**: `{ "num_storeys": 3, "storey_height_m": 3.0 }`
- `PUT /files/{project_id}/verify` **[GATE 1]**
  - **Description**: Human-in-the-loop confirmation of parsed geometry. Freezes an
    immutable verification artifact (audit trail).
  - **Payload**: `{ "confirmed": true, "corrections": [...], "notes": "..." }`

---

## 4. Pipeline Orchestration (`/pipeline`)
High-level endpoints used to orchestrate the pipeline stages automatically.

- `POST /pipeline/{project_id}/run`
  - **Description**: Run full pipeline end-to-end (stops at human gates).
- `POST /pipeline/{project_id}/resume`
  - **Description**: Resume pipeline from the current stage.
- `GET /pipeline/{project_id}/status`
  - **Description**: Full pipeline status overview. Primary endpoint read by the Agent.

---

## 5. Loading (`/loading`)
Accepts load definitions and runs the load combination engine.
**Requirement:** `GEOMETRY_VERIFIED`

- `POST /loading/{project_id}/define`
  - **Description**: Define global loads for the project.
- `POST /loading/{project_id}/combinations`
  - **Description**: Run load combinations. Orchestrates `core.loading` assemblers.
  - **Advances**: project to `LOADING_DEFINED`.
- `GET /loading/{project_id}/output`
  - **Description**: Get full loading output JSON (factored ULS/SLS).

---

## 6. Analysis (`/analysis`)
The structural analysis engine (The "Analyst Agent").
**Requirement:** `LOADING_DEFINED`

- `POST /analysis/{project_id}/run`
  - **Description**: Queue full structural analysis run for all members.
  - **Returns**: `{ "job_id": "...", "status_url": "..." }`
- `GET /analysis/{project_id}/results`
  - **Description**: Return all completed analysis results (Force envelopes, BMD/SFD data).

---

## 7. Design (`/design`)
The design suite for creating reinforcement schedules (The "Designer Agent").
**Requirement:** `ANALYSIS_COMPLETE`

- `POST /design/{project_id}/run`
  - **Description**: Queue a full design run for all members.
- `GET /design/{project_id}/results`
  - **Description**: Return all completed design results (Rebar schedules, etc.).

---

## 8. Reports (`/reports`)
Output and Reporting Layer endpoints.

- `POST /reports/generate`
  - **Description**: Generate calculation sheets or summary reports.
- `GET /reports/{report_id}/preview`
  - **Description**: Render HTML preview for the right-panel IDE.
- `GET /reports/{report_id}/download`
  - **Description**: Download the report as PDF.

---

## 9. Drawings (`/drawings`)
RC detail drawings generated by the Drafter from design results.

- `GET /drawings/{project_id}/member/{member_id}`
  - **Description**: Draw-command set (`section`, `elevation`, `dimensions`,
    `bar_marks`, `annotations`, `canvas_bounds`, `scale`) for a single member.
- `POST /drawings/{project_id}/member/{member_id}/regenerate`
  - **Description**: Regenerate a member's drawing after a design override.
- `GET /drawings/{project_id}/export/dxf`, `GET /drawings/{project_id}/member/{member_id}/export/dxf`
  - **Description**: DXF export (project-level or per-member).

---

## 10. Artifacts (`/artifacts`)
Immutable gate snapshots that form the project audit trail (e.g. the verified
geometry frozen at Gate 1).

- `GET /artifacts/{project_id}` — List artifacts for a project.
- `GET /artifacts/detail/{artifact_id}` — Full artifact content.

---

## 11. Async Jobs (`/jobs`)
- `GET /jobs/{project_id}` / `GET /jobs/{project_id}/{job_id}` — Poll background
  job status (parsing, analysis, design runs).

---

## WebSockets
- `WS /ws/pipeline` — live agent logs / pipeline status (token-authenticated).
- `WS /ws/chat` — agent chat stream (token-authenticated).

---

## Architecture & Infrastructure
- **API**: FastAPI (Python 3.11)
- **Database**: PostgreSQL (SQLAlchemy 2.0 Async) — *optional*; stores default to
  in-memory and must be switched to Postgres via env vars for durability.
- **Job Queue**: in-process `BackgroundTasks`; optional Redis job store (`REDIS_URL`).
- **File Storage**: Local Filesystem / Cloudinary (`FILE_STORAGE_BACKEND`).
- **AI Orchestration**: LangGraph (multi-agent state machine; `MemorySaver` by
  default — see `AUDIT.md` for the persistence gap).
