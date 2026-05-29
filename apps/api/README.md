# Design Suite — API

The FastAPI backend for Design Suite. It exposes a REST API and WebSocket for the structural engineering pipeline, orchestrates a LangGraph multi-agent graph backed by Google Gemini, and enforces four sequential human-confirmation gates before each design phase can proceed.

---

## Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Agent Pipeline](#agent-pipeline)
- [Gate System](#gate-system)
- [Design Codes](#design-codes)
- [Member Types](#member-types)
- [Authentication](#authentication)
- [Storage Backends](#storage-backends)
- [Database](#database)
- [Testing](#testing)
- [Production Deployment](#production-deployment)
- [In Progress](#in-progress)

---

## Tech Stack

| Concern | Library | Version |
|---|---|---|
| Web framework | FastAPI | 0.135.3 |
| ASGI server | Uvicorn | 0.43.0 |
| Agent orchestration | LangGraph | 1.1.6 |
| LLM | google-genai (Gemini) | 1.70.0 |
| ORM | SQLAlchemy (async) | 2.0 |
| Migrations | Alembic | 1.18.4 |
| Auth | fastapi-users | 15.0.5 |
| DB driver | asyncpg | 0.31.0 |
| DXF parsing | ezdxf | 1.4.4 |
| PDF parsing | PyMuPDF | 1.27.2 |
| Email | Resend | 2.30.1 |
| File storage | Cloudinary (optional) | 1.44.2 |
| Type checking | pyrefly | — |

---

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- A [Google Gemini API key](https://aistudio.google.com/app/apikey) (`GEMINI_API_KEY`)
- A [Resend](https://resend.com) account for transactional email (`RESEND_API_KEY`)
- A [Google OAuth application](https://console.cloud.google.com/) for social login (optional)
- Redis (optional — required only if `JOB_STORE_BACKEND=redis`)

---

## Local Development

### 1. Create and activate a virtual environment

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in the required values (see Environment Variables below)
```

### 4. Start PostgreSQL

If you are not using Docker Compose, start PostgreSQL locally and create the database:

```bash
createdb design_suite
```

Update `DATABASE_URL` in `.env` to point to it.

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Start the development server

```bash
uvicorn main:app --reload --port 8000
```

API docs are available at http://localhost:8000/api/docs.

### Type checking

```bash
pyrefly check
```

---

## Environment Variables

All configuration is read from environment variables (or a `.env` file in `apps/api/`).

| Variable | Default | Required | Description |
|---|---|---|---|
| `APP_ENV` | `development` | No | Deployment environment (`development`, `staging`, `production`) |
| `SECRET_KEY` | `change-me-in-production` | **Yes** | JWT signing secret — must be changed in production |
| `JWT_LIFETIME_SECONDS` | `3600` | No | JWT token validity in seconds (default 1 hour) |
| `DATABASE_URL` | — | **Yes** | Async PostgreSQL DSN, e.g. `postgresql+asyncpg://user:pass@localhost/design_suite` |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | No | Comma-separated list of allowed CORS origins |
| `UPLOAD_DIR` | `uploads/` | No | Path for locally stored uploaded files |
| `MAX_UPLOAD_SIZE_MB` | `50` | No | Maximum file upload size in megabytes |
| `FILE_STORAGE_BACKEND` | `local` | No | `local` or `cloudinary` |
| `CLOUDINARY_CLOUD_NAME` | — | If cloudinary | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | — | If cloudinary | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | — | If cloudinary | Cloudinary API secret |
| `JOB_STORE_BACKEND` | `memory` | No | `memory` or `redis` — where background job state is kept |
| `REDIS_URL` | — | If redis | Redis connection URL, e.g. `redis://localhost:6379` |
| `PROJECT_STORE_BACKEND` | `postgres` | No | `memory` (dev/test) or `postgres` |
| `GEMINI_API_KEY` | — | **Yes** | Google Gemini API key for LLM agents |
| `THINKING_MODEL` | `gemini-3.1-flash-lite` | No | Gemini model used for reasoning / planning |
| `ACTION_MODEL` | `gemini-3.1-flash-lite` | No | Gemini model used for tool calls and structured output |
| `RESEND_API_KEY` | — | **Yes** | Resend API key for transactional email |
| `SENDER_EMAIL` | — | **Yes** | From address for outgoing email |
| `GOOGLE_CLIENT_ID` | — | If OAuth | Google OAuth application client ID |
| `GOOGLE_CLIENT_SECRET` | — | If OAuth | Google OAuth application client secret |
| `LOG_LEVEL` | `INFO` | No | Root logging level |

---

## API Reference

All domain endpoints are prefixed `/api/v1/`. Auth endpoints are prefixed `/api/auth/`.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{status, version, environment}` |
| `GET` | `/api/v1/greeting/` | Hello / ping |

### Projects

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/projects/` | Create a new project |
| `GET` | `/api/v1/projects/` | List all projects for the current user |
| `GET` | `/api/v1/projects/{id}` | Fetch a single project |
| `PUT` | `/api/v1/projects/{id}` | Update project metadata |
| `DELETE` | `/api/v1/projects/{id}` | Delete a project |
| `GET` | `/api/v1/projects/{id}/status` | Get current pipeline status |

### Files

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/files/upload/{project_id}` | Upload DXF (+ optional PDF); starts async parse job |
| `GET` | `/api/v1/files/{project_id}/parse-status/{job_id}` | Poll parse job status |
| `GET` | `/api/v1/files/{project_id}/parsed` | Fetch parsed structural JSON |
| `PUT` | `/api/v1/files/{project_id}/verify` | **Gate 1** — confirm parsed geometry |
| `GET` | `/api/v1/files/{project_id}/scale` | Get current drawing scale |
| `PUT` | `/api/v1/files/{project_id}/scale` | Override drawing scale |
| `GET` | `/api/v1/files/{project_id}/files` | List uploaded files for a project |
| `GET` | `/api/v1/files/{project_id}/download/{filename}` | Download a project file |

### Loading

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/loading/{project_id}/define` | Submit load definitions (dead, live, wind, etc.) |
| `GET` | `/api/v1/loading/{project_id}` | Fetch load definitions |
| `PUT` | `/api/v1/loading/{project_id}/member/{member_id}` | Override load on a specific member |
| `POST` | `/api/v1/loading/{project_id}/combinations` | Generate factored ULS/SLS combinations |
| `GET` | `/api/v1/loading/{project_id}/output` | Fetch combination output |
| `POST` | `/api/v1/loading/{project_id}/validate` | Validate load input without saving |

### Analysis

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/analysis/run/{project_id}` | Run FEA on all members |
| `POST` | `/api/v1/analysis/{project_id}/beam` | Analyse a single beam |
| `POST` | `/api/v1/analysis/{project_id}/slab` | Analyse a single slab |
| `POST` | `/api/v1/analysis/{project_id}/column` | Analyse a single column |
| `POST` | `/api/v1/analysis/{project_id}/wall` | Analyse a single wall |
| `POST` | `/api/v1/analysis/{project_id}/footing` | Analyse a single footing |
| `POST` | `/api/v1/analysis/{project_id}/staircase` | Analyse a single staircase |
| `GET` | `/api/v1/analysis/{project_id}/results` | Fetch all analysis results |
| `GET` | `/api/v1/analysis/{project_id}/results/{member_id}` | Fetch result for one member |
| `DELETE` | `/api/v1/analysis/{project_id}/results` | Clear analysis results |
| `GET` | `/api/v1/analysis/{project_id}/status/{job_id}` | Poll analysis job status |

### Design

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/design/run/{project_id}` | Run reinforcement design on all members |
| `POST` | `/api/v1/design/{project_id}/beam` | Design a single beam |
| `POST` | `/api/v1/design/{project_id}/slab` | Design a single slab |
| `POST` | `/api/v1/design/{project_id}/column` | Design a single column |
| `POST` | `/api/v1/design/{project_id}/wall` | Design a single wall |
| `POST` | `/api/v1/design/{project_id}/footing` | Design a single footing |
| `POST` | `/api/v1/design/{project_id}/staircase` | Design a single staircase |
| `GET` | `/api/v1/design/{project_id}/results` | Fetch all design results |
| `PUT` | `/api/v1/design/{project_id}/member/{member_id}` | Edit a member's design parameters |
| `POST` | `/api/v1/design/{project_id}/rerun/{member_id}` | Re-run design for one member |
| `GET` | `/api/v1/design/{project_id}/status/{job_id}` | Poll design job status |

### Drawings

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/drawings/{project_id}/generate` | Generate SVG drawing commands |
| `GET` | `/api/v1/drawings/{project_id}` | Fetch drawing commands |
| `GET` | `/api/v1/drawings/{project_id}/member/{member_id}` | Fetch drawings for one member |
| `POST` | `/api/v1/drawings/{project_id}/member/{member_id}/regenerate` | Regenerate drawings for one member |
| `PUT` | `/api/v1/drawings/{project_id}/confirm` | **Gate 4** — confirm drawing set |
| `GET` | `/api/v1/drawings/{project_id}/layers` | Fetch layer definitions |
| `GET` | `/api/v1/drawings/{project_id}/status/{job_id}` | Poll drawing job status |

### Reports

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/reports/{project_id}/generate` | Generate calculation report PDF |
| `GET` | `/api/v1/reports/{project_id}` | Fetch report metadata |
| `GET` | `/api/v1/reports/{project_id}/download` | Download report PDF |

### Pipeline

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/pipeline/{project_id}/run` | Start the full agent pipeline |
| `POST` | `/api/v1/pipeline/{project_id}/resume` | Resume pipeline after a gate is confirmed |
| `GET` | `/api/v1/pipeline/{project_id}/status` | Get pipeline state |
| `POST` | `/api/v1/pipeline/{project_id}/reset` | Reset pipeline to initial state |
| `GET` | `/api/v1/pipeline/{project_id}/gates` | List gate statuses |
| `POST` | `/api/v1/pipeline/{project_id}/gates/{gate}/confirm` | Confirm a specific gate |

### Jobs

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/jobs/{job_id}` | Get job status and progress |
| `DELETE` | `/api/v1/jobs/{job_id}` | Cancel a job |
| `GET` | `/api/v1/jobs/project/{project_id}` | List all jobs for a project |

### Authentication

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register a new user (triggers email verification) |
| `POST` | `/api/auth/jwt/login` | Log in with email + password |
| `POST` | `/api/auth/jwt/two-factor-verify` | Submit 2FA OTP code |
| `POST` | `/api/auth/request-verify-token` | Re-send email verification link |
| `POST` | `/api/auth/verify` | Verify email from link token |
| `POST` | `/api/auth/forgot-password` | Request password reset email |
| `POST` | `/api/auth/reset-password` | Reset password with token |
| `GET` | `/api/auth/google/authorize` | Begin Google OAuth flow |
| `GET` | `/api/auth/google/callback` | Google OAuth callback (exchange code for token) |
| `GET` | `/api/users/me` | Fetch current user profile |

### WebSocket

| Path | Description |
|---|---|
| `ws://host/ws/{project_id}` | Real-time agent event stream for a project |

---

## Agent Pipeline

The backbone of the backend is a LangGraph `StateGraph`. Every agent node reads from and writes partial updates to a single `StructuralDesignState` object — the canonical record of everything the pipeline knows about a project.

```mermaid
flowchart TD
    START([HTTP trigger /pipeline/run\nor WebSocket message]) --> SUP

    SUP["Supervisor Node\nRoute based on pipeline_status"]

    SUP -->|file_uploaded| PARSE["Parser Node\nDXF/PDF → structural JSON\nNodes · Beams · Columns · Slabs"]
    PARSE --> GATE1{"Gate 1\nAwait engineer confirmation\nPUT /files/{id}/verify"}

    GATE1 -->|confirmed| ANAL["Analyst Node\n2D FEA\nBMD · SFD · Deflections"]
    ANAL --> GATE2{"Gate 2\nAwait load confirmation"}

    GATE2 -->|confirmed| DES["Designer Node\nReinforcement per BS8110 or EC2\nUp to 5 self-weight iterations"]
    DES -->|"Δ self-weight > 5%"| ANAL
    DES -->|converged| GATE3{"Gate 3\nAwait design confirmation"}

    GATE3 -->|confirmed| DRAFT["Drafter Node\nDesign schedules → SVG canvas commands"]
    DRAFT --> GATE4{"Gate 4\nAwait drawing review"}

    GATE4 -->|confirmed| END([Report Generated])
    GATE4 -->|design_change| DES
```

### State object (`StructuralDesignState`)

All nodes share one state object. Key fields:

| Field | Type | Description |
|---|---|---|
| `project_id`, `design_code`, `pipeline_status` | str / int | Project context |
| `messages` | `Annotated[list, add]` | LangChain message history (append-only) |
| `agent_logs` | `Annotated[list, add]` | Structured log entries (append-only) |
| `parsed_structural_json` | dict | Output of the Parser node |
| `geometry_verified` | bool | Gate 1 flag |
| `load_definition`, `loading_output` | dict | Load inputs and factored combinations |
| `analysis_results` | list | FEA results per member |
| `design_results` | list | Reinforcement schedules per member |
| `iteration_count`, `reanalysis_triggered` | int / bool | Self-weight loop tracking |
| `drawing_commands`, `layer_package` | list / dict | Drafter output |
| `current_error`, `retry_count` | str / int | Error handling state |

`messages` and `agent_logs` use LangGraph's `Annotated[list, add]` pattern — nodes append rather than overwrite. All other fields are overwritten by each node.

---

## Gate System

Four hard-stop gates interrupt the pipeline and wait for an HTTP confirmation from the engineer before resuming. Calling any downstream endpoint before its upstream gate is confirmed returns `403 GATE_NOT_PASSED`.

| Gate | Confirmation endpoint | Advances status to |
|---|---|---|
| Gate 1 — Geometry | `PUT /api/v1/files/{id}/verify` | `GEOMETRY_VERIFIED` |
| Gate 2 — Loading | Confirm after `POST .../combinations` | `LOADING_DEFINED` |
| Gate 3 — Design | `POST /api/v1/pipeline/{id}/gates/design/confirm` | `DESIGN_COMPLETE` |
| Gate 4 — Drawings | `PUT /api/v1/drawings/{id}/confirm` | `REPORT_GENERATED` |

Gates are enforced as FastAPI dependencies. For example, the analysis endpoints depend on `require_geometry_verified(project_id)`, which raises an error if `pipeline_status < GEOMETRY_VERIFIED`.

---

## Design Codes

Design Suite currently supports two RC design standards. The code is selected at project creation and stored in `projects.design_code`; the Designer agent uses it to select the correct calculation module at runtime.

### BS8110 (British Standard)

**BS8110-1:1997 — Structural Use of Concrete**

The older British standard for reinforced concrete design, still widely used in the UK and Commonwealth countries (Nigeria, Ghana, Malaysia, etc.). It uses partial safety factors of γ_f = 1.4 (dead) / 1.6 (live) for ULS and works in terms of characteristic cube strength f_cu.

Implemented in `core/design/bs8110/`. Key checks:
- Flexural design (moment redistribution, compression reinforcement)
- Shear design (v_c tables)
- Deflection (span/depth ratio limits)
- Crack width calculation

### Eurocode 2 (EN 1992-1-1)

**Eurocode 2: Design of Concrete Structures**

The European standard for RC design, increasingly adopted globally. It uses partial safety factors γ_G = 1.35 (permanent) / γ_Q = 1.5 (variable) and works in terms of characteristic cylinder strength f_ck.

Implemented in `core/design/ec2/`. Key checks:
- Flexural design (rectangular stress block, biaxial column interaction)
- Shear design (V_Rd,c capacity model)
- Punching shear (for slabs)
- Deflection (deemed-to-satisfy and rigorous methods)
- Crack control (w_k limits)

Both codes produce a reinforcement schedule as output (bar sizes, spacing, link configuration) for each member.

---

## Member Types

| Member Type | Analysis | BS8110 Design | EC2 Design |
|---|---|---|---|
| Beam | 2D FEA (BMD, SFD) | Yes | Yes |
| Slab | One/two-way bending | Yes | Yes |
| Column | Axial + biaxial bending | Yes | Yes |
| Wall | In-plane / out-of-plane | Yes | Yes |
| Footing | Punching + flexure | Yes | Yes |
| Staircase | Longitudinal bending | Yes | Yes |

---

## Authentication

### Registration

1. `POST /api/auth/register` — creates user with `is_verified=False`
2. Verification email sent via Resend
3. User clicks link → `POST /api/auth/verify` — marks `is_verified=True`

Unverified users cannot log in.

### Credentials login

1. `POST /api/auth/jwt/login` (OAuth2PasswordRequestForm)
2. If `is_2fa_enabled` on the user:
   - Backend generates a 6-digit OTP, stores it with a 5-minute expiry, and emails it
   - Response: `{status: "two_factor_required", user_id, email}`
   - Client calls `POST /api/auth/jwt/two-factor-verify` with `{user_id, code}`
3. On success: JWT is issued (`{access_token, token_type: "bearer"}`)

### Google OAuth

1. Frontend redirects to `GET /api/auth/google/authorize`
2. Google auth flow completes
3. Backend handles `GET /api/auth/google/callback`, creates or retrieves the user (Google accounts are pre-verified), and issues a JWT

### Token lifecycle

- Tokens are valid for `JWT_LIFETIME_SECONDS` (default: 3600 s)
- All protected endpoints require `Authorization: Bearer <token>`
- Expired or invalid tokens return `401`; the frontend clears auth state and redirects to `/login`

### Roles

Users have one of three roles: `engineer`, `admin`, or `viewer`. Multi-tenancy is enforced via `organisation_id` — users can only access projects in their own organisation.

---

## Storage Backends

### File storage

| Backend | Config value | Description |
|---|---|---|
| Local filesystem | `FILE_STORAGE_BACKEND=local` | Files saved to `UPLOAD_DIR` (default `uploads/`) |
| Cloudinary | `FILE_STORAGE_BACKEND=cloudinary` | Requires `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` |

Use `local` for development. Use Cloudinary (or any S3-compatible store via a custom adapter) in production.

### Job store

Background jobs (file parsing, analysis, design runs) are tracked in a job store.

| Backend | Config value | Description |
|---|---|---|
| In-memory | `JOB_STORE_BACKEND=memory` | No external dependency; state lost on restart — fine for development |
| Redis | `JOB_STORE_BACKEND=redis` | Persistent, survives restarts; requires `REDIS_URL` |

---

## Database

### Models

| Model | Description |
|---|---|
| `User` | Authenticated user; extends fastapi-users base; includes 2FA and role fields |
| `Organisation` | Multi-tenancy owner; users and projects belong to an organisation |
| `Project` | Core entity; holds design code, pipeline status, and relationships to all sub-entities |
| `ProjectMember` | Each structural member parsed from the uploaded drawing |
| `ProjectGeometry` | Parsed geometry JSON and verification timestamp |
| `ProjectLoad` | Load definition and factored combination output |
| `ProjectAnalysis` | FEA results |
| `ProjectDesign` | Reinforcement design results |
| `ProjectDrawing` | Drawing command payload |

### Migrations (Alembic)

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Auto-generate a migration from model changes
alembic revision --autogenerate -m "add column to projects"
```

---

## Testing

Tests live in `apps/api/tests/`.

```
tests/
├── unit/           # Fast, isolated — analysis, design, loading calculations
├── integration/    # Hit the real database — service and router tests
├── e2e/            # Full pipeline runs
├── benchmarks/     # Performance tests
├── test_auth.py    # Auth and JWT flow tests
├── test_column_design.py
└── test_slab_design.py
```

`pytest.ini` sets `asyncio_mode = auto`, so async test functions work without decorators.

```bash
# Run all tests
pytest

# Run a specific file
pytest tests/unit/analysis/test_beam.py -v

# Run tests matching a name pattern
pytest -k "test_bs8110_beam_flexure" -v

# Run only unit tests
pytest tests/unit/ -v
```

---

## Production Deployment

### Docker

The API has a `Dockerfile` in `apps/api/`. The `docker-compose.yml` at the repository root wires it to PostgreSQL.

```bash
# Build the API image
docker build -t design-suite-api ./apps/api

# Run with docker-compose (recommended)
docker-compose up -d
```

### Environment differences from development

| Concern | Development | Production |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `SECRET_KEY` | Any string | Long random string (never commit) |
| `FILE_STORAGE_BACKEND` | `local` | `cloudinary` (or S3-compatible) |
| `JOB_STORE_BACKEND` | `memory` | `redis` |
| `PROJECT_STORE_BACKEND` | `memory` or `postgres` | `postgres` |
| Database | Local PostgreSQL | Managed PostgreSQL (e.g., RDS, Supabase) |
| CORS `ALLOWED_ORIGINS` | `http://localhost:3000` | Your production frontend URL |

### Checklist

- [ ] `SECRET_KEY` is a unique, secret value (not `change-me-in-production`)
- [ ] `DATABASE_URL` points to a managed PostgreSQL instance with TLS
- [ ] `FILE_STORAGE_BACKEND=cloudinary` with valid Cloudinary credentials
- [ ] `JOB_STORE_BACKEND=redis` with a managed Redis instance
- [ ] `ALLOWED_ORIGINS` contains only your frontend domain
- [ ] `alembic upgrade head` has been run against the production database
- [ ] `APP_ENV=production` disables debug features

---

## In Progress

- **CI/CD:** No GitHub Actions pipeline yet — contributions welcome
- **Redis job store:** Memory backend is default; Redis integration exists but is not tested in CI
- **Additional design codes:** ACI 318 (US), IS 456 (India) are not yet implemented
- **Report generation:** The reports router exists; full PDF generation is partially implemented
