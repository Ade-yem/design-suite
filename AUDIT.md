# Design Suite — Project Audit

_Last updated: 2026-06-16_

A full-stack audit of the Design Suite monorepo against the product goal: an
AI-driven structural-engineering IDE that takes architectural drawings (DXF/PDF)
→ parsed geometry → load takedown → analysis → RC reinforcement design → detailed
drawings, with human-in-the-loop safety gates and an agent chat assistant.

Findings were verified against the code; where an automated pass mis-reported
(e.g. "footing design missing"), the claim was checked and corrected here.

---

## Verdict

The project is a **functional end-to-end product**, roughly **~70% of a
defensible internal/beta MVP** and **~40% of a market-shippable one** for this
(safety-critical) domain. The happy path works today. The distance to market is
dominated by **data durability, a few stubbed members, security hardening, and —
above all — engineering-validation / liability controls**, not by missing
features.

---

## What is genuinely built

- **Full pipeline is real** (not mocked): DXF parsing (ezdxf, 24 unit systems),
  PDF→vision parsing (PyMuPDF + Gemini), the 5-node LangGraph graph with 4
  enforced human-in-the-loop gates, load takedown, closed-form analysis, BS8110
  **and** EC2 RC design for beams/slabs/columns/walls/staircases/**footings**,
  reinforcement scheduling, and PDF calc reports.
- **Frontend ~80–85% and polished**: complete login → project → upload → gate →
  analysis → design → artifacts journey, **live WebSocket** agent chat + progress
  (the older "chat is mocked / WS pending" note is **stale** — it is fully wired),
  robust API client (auth interceptor, friendly error mapping), Zustand stores,
  2FA + Google OAuth + email verification.
- **Security fundamentals mostly right**: JWT + email-verify + OTP 2FA, enforced
  multi-tenancy (`organisation_id` on every store call), magic-byte + size file
  validation, ORM-only (no raw SQL), env-driven secrets, authenticated WebSockets.
- **Infra**: Dockerfiles for both apps, docker-compose, CI (backend pytest +
  frontend lint/build), 60 backend test files, 300 passing.

---

## Maturity scorecard

| Layer / Stage | Maturity | Notes |
|---|---|---|
| DXF/PDF parsing | 85% | Both real; vision is live but consumes LLM calls |
| Loading | 70% | Gravity + system-aware self-weight real; **no wind/lateral, no pattern loading** |
| Analysis | 60% | Closed-form/coefficient solvers, 2-pass. A matrix-stiffness FEA solver exists (`core/analysis/global_solver.py`) but is **unwired** — runtime is closed-form |
| RC design (BS8110/EC2) | 75% | All primary members incl. **footings (pad) work**; some "simplified" wall/column paths |
| Drawings | 50% | Beam/slab/staircase real; **wall + footing generators are stubs (`return []`)**; column simplified |
| Reporting | 90% | Calc sheet, schedule, quantities, PDF all real |
| Orchestration + gates | 90% | Supervisor/analyst/designer real; drafter layer-gen simplified |
| **Persistence** | 40% | **Defaults to in-memory; LangGraph uses `MemorySaver` → all data lost on restart unless Postgres explicitly configured** |
| Frontend | 80% | Full journey + live WS; gaps in mobile, a11y, tests |
| Security | 75% | Strong base; prompt-injection + rate-limiting gaps |
| Ops/CI | 60% | CI runs tests + build; no type-check / e2e / security-scan gate |

### Corrections to note (verified against code)
- **Footing design is NOT missing.** `core/design/rc/bs8110/footing.py:design_pad_footing`
  is fully implemented and `design_member` returns a real footing design (status
  OK, reinforcement). There is **no `NotImplementedError` in `core/design/`**.
- **A 2D matrix-stiffness FEA solver exists** (`GlobalMatrixSolver`,
  `core/analysis/global_solver.py`, tested) but is **not wired** into the
  per-member analysis engine — so the practical state is "runtime analysis is
  closed-form."

---

## Gaps blocking MVP, by category

### A. Data & runtime (P0 — blocks real use)
1. **Persistence defaults to memory + `MemorySaver`** → every project and all
   in-flight pipeline state is lost on restart. The Postgres path and
   `AsyncPostgresSaver` exist but aren't wired into the app lifespan. Biggest
   single blocker. (`apps/api/config.py` default `PROJECT_STORE_BACKEND="memory"`,
   `apps/api/agents/graph.py` `MemorySaver()`.)
2. **Schema isn't migration-managed** — only one Alembic migration exists; the
   rest is `Base.metadata.create_all()`. Production schema-drift risk.

### B. Correctness & domain validation (P0 — safety-critical software)
3. **No independent design-validation story.** Output reinforcement gets built.
   Needs validation against published worked examples, explicit/pinned code
   clauses, documented assumptions, a disclaimer, and an engineer sign-off
   workflow. This is the difference between a demo and software a firm will stake
   its professional-indemnity insurance on.
4. **LLM parameter extraction fails silently** (`agents/analyst.py` broad
   `except: extracted = {}`) — a design can proceed on an incomplete brief
   without the engineer knowing.
5. **Loading gaps**: no wind/lateral/seismic, no pattern (checkerboard) loading.
   Acceptable for gravity frames but must be disclosed.

### C. Security (P0/P1)
6. **LLM prompt injection (HIGH)** — user chat is interpolated raw into the
   analyst extraction prompt (`agents/analyst.py:303`). Manipulating extracted
   loads/grades = under-design. Needs input delimiting + output validation
   against enums.
7. **No rate limiting (MEDIUM)** — upload / analysis / LLM calls are unbounded →
   DoS and runaway API cost.
8. JWT default-secret fallback (mitigated by a non-dev validator) and a low-risk
   file-path canonicalization gap (`storage/file_backends/local.py`).

### D. Feature completeness (P1)
9. **Wall & footing drawing generators are stubs** (`core/drawing/wall.py`,
   `core/drawing/footing.py` return `[]`) — design completes but the engineer
   can't visually review wall/footing reinforcement. Column drawing is simplified.

### E. UI/UX (P1/P2)
10. Not mobile-responsive; **silent session expiry** (401 → redirect, no
    explanation); a few silently-swallowed fetch errors; hardcoded `localhost:5000`
    API base in `apps/web/next.config.ts`; minor a11y gaps (skip links, focus
    traps); unused `react-router-dom` dependency.

### F. Testing / CI (P1)
11. E2E tests are skipped/empty stubs; **no frontend tests**; vision tests hit the
    live LLM (slow/costly); CI has no type-check or security scan.

---

## Distance to MVP & prioritized roadmap

- **Defensible internal/beta MVP (gravity RC frames): ~3–5 focused weeks.**
- **Market / commercial MVP: ~2–4 months**, dominated by validation/liability
  work, not code volume.

### P0 — before anyone relies on it (~2–3 wks)
- Wire Postgres + `AsyncPostgresSaver` as the default deploy config; add a
  full-schema migration. (~2 days)
- Prompt-injection hardening + validate extracted params against allowed enums;
  surface LLM-extraction failures instead of swallowing them. (~3 days)
- Rate limiting (e.g. slowapi) + per-org quotas on upload/analysis/LLM. (~2 days)
- Validation pack: run BS8110/EC2 solvers against published worked examples,
  document assumptions/clauses, add a disclaimer + engineer sign-off gate.
  (~1 wk, ongoing)

### P1 — for a credible product (~2–3 wks)
- Implement wall + footing drawing generators (use the beam generator as the
  template — same `BaseDrawingGenerator` pattern as the staircase generator).
  (~1 wk)
- E2E happy-path test (Playwright) + frontend unit tests; add `tsc`/pyrefly +
  e2e to CI. (~1 wk)
- Session-expiry UX, env-driven API base URL, silent-catch cleanups. (~3 days)

### P2 — maturity / scale
- Wire the existing `GlobalMatrixSolver` for continuous-frame analysis;
  wind/pattern loading; mobile responsiveness; error tracking (Sentry); audit
  logging; deferred backlog (strip-footing auto-detect, staircase-type spanning
  model, footing-type override → reanalysis).

---

## The one thing to stress

This is **safety-critical software** — the output is reinforcement poured into
buildings. The codebase is impressively complete on *features*; the gap to market
is disproportionately about **trust infrastructure** (durable data, validated
calculations, transparent assumptions, prompt-injection resistance, professional
sign-off/liability workflow) rather than new features. Prioritize those over
breadth.
