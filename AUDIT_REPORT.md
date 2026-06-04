# Design Suite — Implementation Audit

**Scope:** End-to-end flow from authentication → project creation → DXF/PDF upload →
geometry parsing → engineer verification (Safety Gate 1).
**Perspective:** Senior full-stack review (security, correctness, concurrency, UX).
**Method:** Direct source reading of `apps/api` and `apps/web`, corroborated across
four parallel subsystem deep-dives. Every Critical/High finding below carries a
`file:line` anchor and was verified first-hand.

---

## 1. Executive Summary

The architecture is sound and genuinely well-layered (router → service → core,
LangGraph agent pipeline, pluggable stores, human-in-the-loop gates). The
**happy-path works**, but the seam between the three runtimes — the **REST/DB
status machine**, the **LangGraph checkpointer**, and the **in-memory caches** —
is where correctness and security break down.

The single most important theme: **three separate sources of truth for "where is
this project in the pipeline?" that are never reconciled** — `Project.pipeline_status`
(DB), the LangGraph gate flags (`geometry_verified`, …), and the in-memory
`_GeometryStore`. Most Critical/High findings trace back to this.

| Severity | Count | Headline issues |
|----------|-------|-----------------|
| 🔴 Critical | 5 | Tenant-isolation bypass on null org; default JWT secret; unauthenticated WebSocket; pipeline state on MemorySaver; dead gate-flag path + stubbed resume |
| 🟠 High | 8 | Engineer corrections never applied; `verified_at` never persisted; JWT in URL + localStorage; unvalidated LLM output / prompt injection; parse↔verify race; no upload content validation; no verify locking; unauthenticated parse-status |
| 🟡 Medium | 9 | Weak OTP RNG; plaintext OTP; permissive CORS; no token refresh; non-thread-safe singletons; scale not enforced; PDF default span/scale; shared token secret; no DXF entity cap |
| ⚪ Low | 5 | Client-only guard; no PKCE; WS reconnect UX; secret in logs; unthrottled progress |

---

## 2. End-to-End Flow (as built)

1. **Register** (`POST /api/auth/register`) → user created `is_verified=false`; an
   Organisation is auto-created in `on_after_register` (`auth/manager.py:145-182`);
   verification email sent.
2. **Verify email** → `is_verified=true`. **Login** (`/api/auth/jwt/login`) enforces
   `is_active` + `is_verified`; if `is_2fa_enabled`, issues a 6-digit email OTP and
   returns `two_factor_required`; otherwise returns a JWT.
3. **Frontend** stores `{user, token, org}` in Zustand → `localStorage`
   (`authStore.ts:124`). Axios injects `Bearer` on every request
   (`lib/api.ts:27-38`); 401 → full logout.
4. **Create project** (`routers/projects.py:106`) stamps `organisation_id` +
   `created_by` from the JWT user.
5. **Upload** (`POST /api/v1/files/upload/{id}`) saves the DXF (+optional PDF) and
   queues a **background parse** (`routers/files.py:230-243`).
6. **Parse** runs off-loop (`services/files.py:162`, `asyncio.to_thread`): `ezdxf`
   for DXF / `pymupdf` for PDF → normalize to mm → if no members classified, an
   LLM (Gemini) extraction pass runs → status advances to `FILE_UPLOADED`.
7. **Frontend** polls `parse-status`, fetches `/parsed`, renders the canvas, shows
   the scale-confirmation banner and the Gate-1 verification bar.
8. **Verify** (`PUT /api/v1/files/{id}/verify`) → status advances to
   `GEOMETRY_VERIFIED`, unlocking loading/analysis.

---

## 3. Critical Findings

### 🔴 C1 — Tenant isolation silently disabled when `organisation_id` is `NULL`
**Where:** `storage/project_store.py:101,118,137,154,281,338,369`; `dependencies.py:55`;
failure path `auth/manager.py:183`.
Every tenancy check is written as `if organisation_id is not None: <scope by org>`.
`get_project` passes `user.organisation_id` (`dependencies.py:55`). If a user's
`organisation_id` is `NULL`, the filter is **skipped entirely** and that user can
read/modify/delete **any project in any tenant**.
Org auto-creation is best-effort and swallows failures (`manager.py:183` `except`),
leaving the user with a `NULL` org — and the migration explicitly made the column
nullable. Superusers are also `NULL` by design.
**Impact:** Cross-tenant data access (confidentiality + integrity breach).
**Fix:** Treat `NULL` org as "match nothing," not "match all." Make `organisation_id`
non-nullable for non-superusers; fail registration hard if org creation fails; add a
dedicated superuser path rather than relying on `NULL`.

> Note: a parallel review reported tenancy as "properly enforced." It verified the
> filter *exists* but did not exercise the `NULL` path. The bypass is real.

### 🔴 C2 — Default JWT signing secret shipped in code
**Where:** `config.py:92` — `SECRET_KEY = os.getenv("SECRET_KEY") or "change-me-in-production"`.
Same secret also signs password-reset and email-verification tokens
(`auth/manager.py:56-57`). No startup assertion that it was overridden.
**Impact:** If unset in prod, anyone can forge valid tokens for any user → full
auth bypass.
**Fix:** Fail fast at boot when `APP_ENV != development` and `SECRET_KEY` is the
default/empty. Use distinct secrets per token purpose.

### 🔴 C3 — WebSocket pipeline endpoint has no authentication
**Where:** `websocket.py:56-58` (`/ws/{project_id}`) — connects with no auth; no
project ownership check. The frontend appends `?token=` (`useProjectSocket.ts`) but
the **backend never reads or validates it**.
**Impact:** Anyone who knows/guesses a `project_id` can stream all agent messages and
**drive the pipeline** (send chat → trigger agents) for someone else's project.
**Fix:** Authenticate on `accept` (parse the JWT from the query/subprotocol, resolve
the user, enforce the same org scoping as REST), then reject on failure.

### 🔴 C4 — Pipeline state defaults to in-memory `MemorySaver`
**Where:** `agents/graph.py:131-138`. The lifespan I recently added
(`main.py`) swaps in `AsyncPostgresSaver` when `DATABASE_URL` is set, but the
**default and the fallback are still `MemorySaver`**.
**Impact:** On restart, all mid-pipeline checkpoint state is lost; with
`uvicorn --workers N` each worker has its own memory, so a request/WS landing on a
different worker sees no state. Horizontal scaling silently breaks gates.
**Fix:** Require the Postgres checkpointer in non-dev; treat a failed checkpointer
init as fatal in prod rather than degrading to memory. (Lifespan wiring already
landed — finish it by making prod fallback hard-fail.)

### 🔴 C5 — Two unsynchronized advancement mechanisms; resume button is a stub
**Where:** `agents/gates.py:10-24` vs `agents/supervisor.py:27-39`;
`routers/pipeline.py:123-157`; `components/ChatSidebar.tsx:173-195`.
The pipeline can advance **only** via `supervisor_router`, which routes on
`pipeline_status` (DB-backed, updated by REST `/verify`). The gate-node flags
(`geometry_verified`, `loading_confirmed`, …) are **never set by any HTTP path**, so
the gate nodes are effectively dead code and `interrupt_before` is the only real
pause. Meanwhile the UI's "Approve & Continue" button calls `/pipeline/resume`, whose
background task is an explicit stub ("real pipeline would invoke each service…",
`pipeline.py:148-153`) — it marks the job complete without doing anything.
**Impact:** Confusing, fragile control flow; the visible resume affordance does
nothing; progression actually depends on the user sending another chat message so the
supervisor re-routes. Easy to mis-modify into a real deadlock.
**Fix:** Pick one source of truth. Either (a) delete the gate-flag nodes and make the
supervisor+`pipeline_status` the canonical machine, or (b) bridge `/verify` into the
checkpointer (`graph.update_state(config, {"geometry_verified": True})`) and make
`/resume` actually re-invoke the graph with `None` input to continue from the
interrupt. Then wire the button to the real path.

---

## 4. High Findings

### 🟠 H1 — Engineer's geometry corrections are recorded but never applied
**Where:** `services/files.py:348-350`. `verify_geometry` stores the payload as
`parsed["user_corrections"] = corrections` but **never mutates `parsed["members"]`** —
the array that loading/analysis consume. Frontend edits/deletes
(`canvasStore.updateMember/deleteMember`) therefore have **no downstream effect**.
**Impact:** The core purpose of Safety Gate 1 — letting the engineer fix the AI's
mistakes before analysis — is silently defeated. The engineer believes their
corrections are authoritative; the solver uses the original AI output.
**Fix:** Apply corrections into the canonical member list (add/update/delete by
`member_id`), validate them against a schema, then persist the merged geometry.

### 🟠 H2 — `verified_at` is never persisted
**Where:** `services/files.py:352-367`; column `db/models/project.py` `ProjectGeometry.verified_at`.
The method returns a fresh `verified_at` timestamp to the client but never writes it
to the row; `_db_save_geometry` doesn't set it. The DB column stays `NULL`.
**Impact:** No durable record of who/when geometry was approved → no audit trail, and
any logic relying on `verified_at` is dead.
**Fix:** Set `verified_at = now()` (and ideally `verified_by`) inside the same save.

### 🟠 H3 — JWT exposed via OAuth redirect URL and localStorage
**Where:** `auth/router.py:457` redirects to `…/auth/callback?token=<jwt>`;
`authStore.ts:124` persists the token to `localStorage`.
**Impact:** Token leaks into browser history, `Referer` headers, proxy/access logs;
and is readable by any XSS. 1-hour lifetime widens the window.
**Fix:** Deliver the token via a short-lived single-use code or `httpOnly; Secure;
SameSite` cookie; avoid query-string tokens; consider memory + silent refresh.

### 🟠 H4 — LLM member output is unvalidated; prompt-injection surface
**Where:** `agents/parser.py` (~`533-682`, `833-931`). LLM JSON is `json.loads`/
`ast.literal_eval`'d with post-hoc defaulting but **no schema validation**; on parse
failure it silently falls back to stub members (e.g. 300×300, span 3 m). DXF layer
names / text / block names are embedded into prompts unsanitized.
**Impact:** Hallucinated or attacker-influenced members (via crafted layer names) flow
into structural calculations; silent stubbing hides failures from the engineer.
**Fix:** Validate against a strict Pydantic schema; reject/flag on failure instead of
stubbing; sanitize/escape drawing-derived text before prompting; cross-check members
against actual DXF geometry.

### 🟠 H5 — Async parse can overwrite verified geometry (race)
**Where:** `services/files.py` `parse()` vs `verify_geometry()`; gate only checks
`require_file_uploaded` (status), not parse-job completion.
**Impact:** If the engineer verifies against an early/preview state while the
background parse is still running, the later parse overwrites geometry and the stored
corrections reference stale `member_id`s.
**Fix:** Gate verification on parse-job completion; lock geometry once verified;
version the geometry blob.

### 🟠 H6 — No content validation or malware scanning on upload
**Where:** `routers/files.py:230` → `file_handler.save`; only extension + 50 MB size
are checked. `ACCEPTED_MIME_TYPES` exists in config but is **never enforced**; no magic
bytes, no AV.
**Impact:** Arbitrary binaries accepted as `.dxf`/`.pdf`; stored files trusted blindly.
**Fix:** Validate magic bytes / MIME, cap entity counts, run AV (e.g. ClamAV) before
parsing.

### 🟠 H7 — Concurrent `/verify` is last-write-wins
**Where:** `routers/files.py:316-366`. No ETag/version/optimistic lock.
**Impact:** Two engineers verifying the same project silently clobber each other; no
record of which confirmation won.
**Fix:** Optimistic concurrency (version or `updated_at` precondition); 409 on conflict.

### 🟠 H8 — `parse-status` endpoint is unauthenticated
**Where:** `routers/files.py:258` — `get_parse_status(project_id, job_id)` has no
`Depends`. Unlike its siblings it neither authenticates nor scopes by org.
**Impact:** Job state / existence disclosure for arbitrary project+job IDs.
**Fix:** Add `Depends(get_project)` (or at least `current_active_user`).

---

## 5. Medium Findings

- **🟡 M1 — Weak OTP randomness.** `random.randint(100000, 999999)` (`auth/router.py:130`)
  is not cryptographically secure. Use `secrets.randbelow`.
- **🟡 M2 — OTP stored in plaintext.** `User.two_factor_code` is plaintext; hash it and
  compare in constant time.
- **🟡 M3 — Permissive CORS.** `allow_methods=["*"]`, `allow_headers=["*"]` with
  `allow_credentials=True` (`main.py`). Pin explicit methods/headers.
- **🟡 M4 — No token refresh.** 401 → hard logout (`lib/api.ts:42-70`); 1-hour JWT means
  hourly forced re-login. Add refresh-token rotation.
- **🟡 M5 — In-memory singletons not concurrency-safe.** `_GeometryStore` and the other
  module-level stores (`services/files.py:52-120`) are plain dicts; unsafe across
  workers and racy under concurrent requests for one project.
- **🟡 M6 — Scale confirmation not enforced.** The banner exists, but `/verify` doesn't
  require `scale.confirmed`; `dxf_parser.py:460-481` can silently override scale.
  Engineer can proceed on an unconfirmed/overridden scale.
- **🟡 M7 — PDF parsing defaults are silently wrong.** `pdf_parser.py` defaults scale to
  mm (`0.001`) and span to `5.0 m`. A metric PDF yields a 1000× error with only a soft
  warning.
- **🟡 M8 — One secret for all token types.** JWT, reset, and verify tokens share
  `SECRET_KEY`. Separate them.
- **🟡 M9 — No DXF entity cap.** A crafted DXF with millions of entities can exhaust
  memory in the parse thread. Enforce a limit.

## 6. Low Findings

- **⚪ L1** AuthGuard is client-side only (`components/AuthGuard.tsx`) — fine, since REST
  is server-guarded, but don't rely on it for protection.
- **⚪ L2** No PKCE on the OAuth flow (best practice for SPA clients).
- **⚪ L3** WebSocket reconnect/“disconnected” UX is thin; no auth-failure surface.
- **⚪ L4** Cloudinary backend can log `api_secret` in exception paths — redact.
- **⚪ L5** Job progress broadcasts on every tick — throttle to protect slow clients.

---

## 7. What's Done Well

- **CPU-bound parsing is correctly off-loaded** to a thread (`services/files.py:162`) —
  the event loop is not blocked.
- **Stage-gate sequencing is enforced at the REST layer** via dependency injectors
  (`dependencies.py`) — downstream calls 403 until the upstream gate passes (when an
  org is present).
- **Auth fundamentals are mostly solid:** email-verification gate, 2FA replay
  protection + expiry handling, OAuth associate-by-email, reset blocked for
  OAuth-only users.
- **Clean layering and seams for production:** `build_app(checkpointer)` factory,
  pluggable project/job/file backends, `ensure_cached` DB-fallback reads, and the
  recently added FK `ON DELETE CASCADE` + indexes + Postgres-checkpointer lifespan.

---

## 8. Prioritized Remediation Roadmap

**P0 — close before any real multi-user/prod use**
1. C1 tenant-isolation `NULL`-org bypass (treat null as deny; org non-null for users).
2. C2 enforce non-default `SECRET_KEY` at boot; split token secrets.
3. C3 authenticate + org-scope the WebSocket.
4. C4 require the Postgres checkpointer in prod (no memory fallback).

**P1 — correctness of the core promise (Gate 1)**
5. H1 actually apply engineer corrections to the member list.
6. C5 unify the advance mechanism and make `/resume` + the UI button real.
7. H2 persist `verified_at`/`verified_by`; H5 close the parse↔verify race; H7 add
   optimistic locking.

**P2 — input trust & hardening**
8. H4 validate LLM output + sanitize prompts; H6 file content/AV validation; M9 entity
   cap; M6/M7 scale/units enforcement.

**P3 — auth hygiene & UX**
9. H3 token transport/storage; H8 auth on parse-status; M1–M4, M8 OTP/CORS/refresh.

---

*Generated as a point-in-time review of the working tree. File:line anchors reference
the state of the branch at audit time.*
