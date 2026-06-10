# Backend Test Suite Audit

**Scope:** `apps/api` test suites (`tests/`), Gemini/LLM call sites, store usage, and environment-variable handling.
**Status:** Findings only — no code changed yet.
**Date:** 2026-06-04

---

## TL;DR

The backend test suite **cannot currently pass in CI**. There are three hard blockers that stop _collection_ (so even pure arithmetic unit tests fail), one suite that makes **live Gemini API calls**, and a class of API integration tests that are **silently broken** because they never authenticate. On top of that there is dead/scratch code in the test tree and inconsistent layout.

The CI workflow (`.github/workflows/ci.yml`) runs `pytest` with **only** `PROJECT_STORE_BACKEND=memory` set — no `GEMINI_API_KEY`, no database — which trips blockers #1 and #2 below immediately.

---

## A. Blockers — these stop the whole suite from collecting

### A1. Module-level LLM instantiation requires an API key at import time ⛔ (highest impact)

`agents/analyst.py:37` and `agents/designer.py:33` build a `ChatGoogleGenerativeAI` client **at module import**:

```python
# agents/analyst.py
_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=settings.GEMINI_API_KEY)
# agents/designer.py
_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)
```

Import chain: `tests/conftest.py` → `from main import app` → `routers/chat.py` → `import agents.graph` → `agents.analyst` / `agents.designer` → LLM constructed. With no key, `langchain_google_genai` raises:

```
ValidationError: API key required for Gemini Developer API.
```

**Consequence:** _Every_ test — including `tests/unit/storage/test_artifact_store.py`, which touches no LLM — fails at collection because `conftest` imports `main`. Confirmed locally: collecting the artifact-store unit test errors out unless `GEMINI_API_KEY`/`GOOGLE_API_KEY` is exported. CI does not export it, so the backend job is red.

Note the inconsistency that complicates mocking:
| Agent | Model | Key source | Seam |
|-------|-------|-----------|------|
| `parser.py` | `settings.ACTION_MODEL` | `settings.GEMINI_API_KEY` | **lazy** `_get_llm()` ✅ |
| `analyst.py` | hard-coded `gemini-1.5-pro` | `settings.GEMINI_API_KEY` | **module-level** `_llm` |
| `designer.py` | hard-coded `gemini-1.5-pro` | env (no param passed) | **module-level** `_llm` |

### A2. `tests/beam_8110/test_analysis.py` imports a non-existent module ⛔

```python
from core.loading.beam_analysis import BeamAnalysis   # module does not exist
```

`core/loading/` has no `beam_analysis` module. This raises `ModuleNotFoundError` during collection, and because it's a collection-time error it **aborts the entire `pytest` run** (164 tests collected, 1 error → interrupted).

### A3. `PROJECT_STORE_BACKEND` has no safe default ⚠️

`config.py:121`:

```python
PROJECT_STORE_BACKEND: Literal["memory", "postgres"] = cast(Literal[...], os.getenv("PROJECT_STORE_BACKEND"))
```

Unlike every other setting (which uses `os.getenv(...) or "<default>"`), this resolves to `None` when the env var is missing, and `None` fails `Literal["memory","postgres"]` validation → `Settings()` construction crashes. It works today only because `tests/conftest.py` sets the env var at import and CI sets it explicitly. Any other entry point (a script importing `config`, a developer running a single file) crashes with a confusing pydantic error.

---

## B. Live external calls / network dependence

### B1. The Vision/Parser suite is "zero-mock" and calls Gemini for real

`tests/integration/agents/test_vision_agent.py` (docstring: _"zero-mock, real-world integration test suite … real Gemini LLM"_) calls `_run_member_extraction(...)` and `parser_node(...)`, which hit the live Gemini API and cost money / require network.

### B2. …but it can never actually run — hard-coded absolute paths

All five tests reference the maintainer's personal machine:

```python
dxf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.dxf"
pdf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.pdf"
```

Each test does `if not os.path.exists(dxf_path): pytest.skip(...)`. These paths don't exist in the repo or CI, so **every test in this file is permanently skipped** — the suite is simultaneously dangerous (live calls) and dead (always skipped).

Meanwhile, real sample files _do_ exist in-repo under `uploads/` (e.g. `uploads/PRJ-BCD1A535/..._Floor-beam.dxf` / `.pdf`), so the parsing portion could be exercised offline against a committed fixture.

---

## C. Database / Postgres requirements

### C1. Authenticated API tests break in memory mode (and aren't authenticated anyway)

`tests/integration/api/test_loading_router.py` and `tests/integration/pipeline/test_loading_to_analysis.py::TestGateEnforcement` call endpoints guarded by `current_active_user` (via `require_geometry_verified` etc.). The fastapi-users dependency chain resolves `get_async_session`, which raises `RuntimeError: DATABASE_URL is not set` in memory mode — so the request 500s instead of returning the asserted `403`/`201`. Confirmed locally.

Even with a real database wired in, these tests send **no `Authorization` header and install no dependency override**, so they would get `401`, not the asserted status. There is no login/token helper anywhere in `tests/`. **These tests cannot pass in either configuration as written.**

### C2. The working pattern already exists (and is the fix)

`tests/integration/api/test_artifacts_router.py` overrides `current_active_user` via `app.dependency_overrides` with a stub user, so it runs fully in-memory with no DB and no token. This is the pattern the other API tests need (ideally hoisted into a shared `conftest` fixture / authenticated client).

### C3. Vestigial DB-engine teardown in a memory-only test

`tests/unit/test_project_store_batch.py` has an autouse `cleanup_db_connections` fixture that disposes `db.session._engine`. In memory mode the engine is never created, so this is a no-op that misleadingly implies the test runs against Postgres.

---

## D. Store cleanup / cross-test isolation

### D1. `file_service` geometry cache is never reset between tests ⚠️

`services/files.py:121` holds a module-level singleton `_store = _GeometryStore()` caching parsed geometry and scale per project. `tests/conftest.py::clear_stores` resets `project_store` and (now) `artifact_store`, but **not** `file_service._store`. Parsed geometry/scale therefore leak across tests, which can cause order-dependent passes/failures once geometry-touching tests are unskipped.

### D2. `job_store` is not reset either

The job store singleton (`storage/job_store.py`) is not cleared in `conftest`. Lower risk today (few tests use it), but the same isolation gap.

### D3. What _is_ handled

`clear_stores` (autouse) correctly clears `project_store._projects/_members` and `artifact_store.clear()`. The intent is right; it's just incomplete.

---

## E. Things that don't make sense / cruft

| #   | Item                                                                           | Issue                                                                                                                                                                                                                                                 |
| --- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | `tests/scratch_debug.py`, `_2.py`, `_3.py`                                     | `print`-based debug scripts, **no assertions**. Not collected (don't match `test_*`) but pollute the test tree.                                                                                                                                       |
| E2  | `tests/benchmarks/bs8110_worked_examples.py`                                   | Not a `test_*` file → never collected; unclear why it lives under `tests/`.                                                                                                                                                                           |
| E3  | `tests/test_slab_design.py` (144 L) vs `tests/slab/test_slab_design.py` (59 L) | Overlapping/duplicate slab-design coverage in two places.                                                                                                                                                                                             |
| E4  | Layout sprawl                                                                  | Calc/design tests live at `tests/` root (`test_column_design.py`, `test_slab_design.py`), under `tests/slab/`, `tests/beam_8110/`, **and** `tests/unit/design/`. No single convention; `tests/unit/` is the apparent intent.                          |
| E5  | `tests/e2e/test_full_pipeline_bs8110.py`, `test_canvas_interactions.py`        | Entirely `@pytest.mark.skip` empty-body stubs; canvas tests reference a `live_server` fixture that doesn't exist.                                                                                                                                     |
| E6  | `conftest` stub fixtures                                                       | `project_with_loads_defined`, `project_with_analysis_complete`, `project_with_design_failures` return unpopulated/`test_project` stubs; the integration tests depending on them are `skip`-ped, so they're placeholders that would fail if unskipped. |
| E7  | `pytest.ini` `addopts = -v --tb=short`                                         | Always-verbose; cosmetic, not a blocker.                                                                                                                                                                                                              |

---

## F. Environment-variable usage map (for reference)

| Variable                  | Where                                         | Default if unset      | Test impact                                             |
| ------------------------- | --------------------------------------------- | --------------------- | ------------------------------------------------------- |
| `PROJECT_STORE_BACKEND`   | `config.py:121`                               | **none → crash** (A3) | conftest sets `memory`; CI sets `memory`                |
| `GEMINI_API_KEY`          | `config.py:128`, used in `analyst`/`parser`   | `""`                  | empty value still breaks import-time LLM build (A1)     |
| `GOOGLE_API_KEY`          | read by langchain in `designer.py` (no param) | —                     | needed for designer import unless refactored            |
| `DATABASE_URL`            | `config.py:123`, `db/session.py`              | `None`                | postgres store / auth chain raise `RuntimeError` (C1)   |
| `REDIS_URL`               | `config.py:111`                               | `None`                | promotes job store to redis if set; fine for tests      |
| `GOOGLE_CLIENT_ID/SECRET` | `config.py` / `auth`                          | `""`                  | logs a warning ("Google OAuth is missing …"); non-fatal |

The only var CI provides is `PROJECT_STORE_BACKEND`. Locally, the minimum needed to _collect_ today is `PROJECT_STORE_BACKEND=memory GEMINI_API_KEY=dummy GOOGLE_API_KEY=dummy`.

---

## G. Proposed remediation (for approval — not yet implemented)

Ordered by leverage:

1. **Make LLM construction lazy + mockable (fixes A1).**
   Refactor `analyst.py` and `designer.py` to a lazy `_get_llm()` (matching `parser.py`), so importing the package never calls the network or needs a key. Then add an **autouse fixture in `tests/conftest.py`** that patches `agents.parser._get_llm`, `agents.analyst._get_llm`, `agents.designer._get_llm` (and `routers/greeting.py`'s lazy client) to return a fake whose `.ainvoke`/`.invoke` yields canned responses. Belt-and-suspenders: set dummy `GEMINI_API_KEY`/`GOOGLE_API_KEY` in `conftest` so any missed seam still imports.

2. **Fix or quarantine `tests/beam_8110/test_analysis.py` (fixes A2).**
   Correct the import to the real module, or mark the file as a known-broken xfail/skip, so collection completes. (Need to confirm what `BeamAnalysis` was meant to be.)

3. **Give `PROJECT_STORE_BACKEND` a default (fixes A3):** `os.getenv("PROJECT_STORE_BACKEND") or "memory"`.

4. **Force memory + full store reset (D1/D2):** keep `PROJECT_STORE_BACKEND=memory` in `conftest`, and extend `clear_stores` to also reset `file_service._store` (add a `clear_all()`/reset helper) and the job store.

5. **Shared authenticated client (fixes C1):** add an `auth_client` fixture (or global `current_active_user` override) in `conftest`, and point `test_loading_router.py` / `TestGateEnforcement` at it so they assert real gate behaviour instead of crashing.

6. **Rework the Vision suite (B1/B2):** mock the LLM seam from step 1, and read the committed `uploads/.../Floor-beam.dxf` fixture (or a small committed sample) instead of the hard-coded home-directory paths. Keep one optional, explicitly-marked (`@pytest.mark.live`) real-API test gated behind an env flag if a true smoke test is desired.

7. **Housekeeping (E1–E6):** delete/relocate `scratch_debug*` and `benchmarks`, de-duplicate the slab tests, consolidate calc tests under `tests/unit/`, and either implement or remove the empty e2e stubs and unused stub fixtures.

### In-scope for the requested change set

The user's explicit asks map to: **#1 (mock Gemini), #3+#4 (memory stores everywhere + cleared after each test)**, plus the env-var blockers surfaced here (#2, #3). Items #5–#7 are recommended follow-ups.
