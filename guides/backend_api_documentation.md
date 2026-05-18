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

## 1. Authentication & Users (`/auth`, `/users`)
Powered by `fastapi-users`.

- `POST /auth/register`
  - **Description**: Register a new user.
  - **Payload**: `{ "email": "...", "password": "...", "full_name": "...", "organisation_id": "..." }`
- `POST /auth/jwt/login`
  - **Description**: Login and receive a JWT token.
  - **Payload**: `username` (email) and `password` (form-data).
- `POST /auth/jwt/logout`
  - **Description**: Revoke the current JWT token.
- `GET /users/me`
  - **Description**: Get current authenticated user profile.
- `PATCH /users/me`
  - **Description**: Update user profile (name, etc.).

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
- `PUT /files/{project_id}/verify` **[GATE 1]**
  - **Description**: Human-in-the-loop confirmation of parsed geometry.
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

## Architecture & Infrastructure
- **API**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL (SQLAlchemy 2.0 Async)
- **Job Queue**: Redis (BackgroundTasks/Celery)
- **File Storage**: Local Filesystem / Cloudinary
- **AI Orchestration**: LangGraph (Multi-agent state machine)
