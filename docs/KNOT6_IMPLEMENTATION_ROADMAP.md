# KNOT6 — Implementation Roadmap

> Builds on [`KNOT6_ARCHITECTURE.md`](KNOT6_ARCHITECTURE.md) (current state) and
> [`KNOT6_KEEP_MODIFY_ADD.md`](KNOT6_KEEP_MODIFY_ADD.md) (per-component decisions). Guiding
> principle: **existing working intelligence engine → preserve → extend → build KNOT6 around it.**
> Nothing below authorizes work past Phase 0 — each phase begins only once explicitly started.

---

## Phase 0 — Foundation — ✅ COMPLETE

**Objective:** Establish a verified, documented, safe-to-build-on baseline without changing any
product behavior.

**Features:** None (infrastructure/process only) — `knot6-development` branch, verified test/build
status, baseline documentation.

**Existing code reused:** All of it, unmodified.

**New code required:** None. Three documentation files (this roadmap, the architecture doc, the
keep/modify/add ledger).

**Dependencies:** None added to either `requirements.txt` or `package.json`.

**Acceptance criteria:**
- [x] `knot6-development` branch created off `master`.
- [x] Existing backend test suite run and recorded (11/12 pass, 1 model-version-dependent failure,
      documented — not fixed).
- [x] Backend confirmed to start and serve the auto-seeded demo dataset.
- [x] Frontend confirmed to typecheck, build, and serve.
- [x] Full pipeline (ingest → extract → resolve → graph → analyze → API → frontend-consumable
      response) verified live against the running backend.
- [x] Three baseline docs committed.

---

## Phase 1 — Investigation / Case / Persistence — ✅ COMPLETE

**Status:** Implemented, tested (31/32 tests passing — 1 pre-existing documented failure carried
over unchanged from Phase 0), and documented. See
[`KNOT6_ARCHITECTURE.md`](KNOT6_ARCHITECTURE.md) for the verified current state and the Phase 1
completion report (delivered separately) for the full change list. Delivered as originally scoped
below, with two changes worth flagging explicitly:

- **`requirements.txt` was updated directly** (Phase 0 deliberately left it untouched and only
  *recorded* findings) — unavoidable, since Phase 1's own code needs `sqlalchemy`/`alembic`/
  `psycopg[binary]` to run at all, plus a `bcrypt==4.0.1` pin discovered when the password hash/
  verify path was exercised for the first time (see `KNOT6_ARCHITECTURE.md` §10).
- **Every pre-existing frontend screen became investigation-aware**, not just the three new ones —
  found to be necessary, not optional, once real data started flowing through
  `ScopedGraphStore` (see `KNOT6_ARCHITECTURE.md` §7's note on the ID-namespacing leak this closed).

**Objective:** Give KNOT6 a real persistence layer and a case/investigation concept, so every later
phase has something to scope work to instead of one flat global graph.

**Features:**
- PostgreSQL-backed `users`, `cases`, `case_members` tables.
- Case-scoped graph writes: every node/edge tagged with the active `case_id`.
- Case list + case detail/workspace screen (new "Investigations" nav area).
- A fourth RBAC role, **Viewer** (read-only), alongside the existing Admin/Investigator/Analyst.
- Per-case authorization (a user must be a member of a case to read/write its data).

**Existing code reused:**
- `GraphStore` interface (`app/db/graph_store.py`) — extend, don't replace; `case_id` becomes an
  additional node/edge attribute the existing NetworkX/Neo4j implementations already have room for.
- `app/graph/schema.py`'s already-declared `CASE` node type and `LINKED_TO_CASE` relation — wire
  them up rather than invent new ones.
- `app/api/deps.py`'s `require_role()` pattern — extend with a `require_case_access()` sibling, same
  shape.
- Existing ingestion routes (`app/api/routes/ingestion.py`) — add a required `case_id` parameter,
  logic otherwise unchanged.

**New code required:**
- SQLAlchemy models + Alembic migrations for `users`, `cases`, `case_members`.
- A Postgres session/connection module (new, e.g. `app/db/postgres.py`), separate from
  `graph_store.py`.
- `app/api/routes/cases.py` (new router: create/list/get case, add/remove member).
- Frontend: `src/pages/Investigations.tsx` (list) + a case workspace shell; nav entry.

**Dependencies:** `sqlalchemy`, `asyncpg` or `psycopg[binary]`, `alembic` (backend). None new on the
frontend.

**Acceptance criteria:**
- A new case can be created, and only entities/relations ingested under that case appear in its
  graph/analytics/search results.
- A user who is not a case member gets a 403 on that case's routes.
- Existing global-graph behavior (today's single-case-equivalent demo data) still works — migrate
  the demo dataset into one seeded "Demo Investigation" case rather than deleting it.
- Existing test suite still passes; new tests cover case creation and case-scoped isolation.

---

## Phase 2 — Intelligence Core

**Objective:** Turn the already-working analytics engine into the investigative surface the PS
actually asks for: a real network explorer (3D-capable) with explainable key-person detection and
hidden-relationship discovery — without touching the analytics logic itself.

**Features:**
- 3D Network Explorer (alongside, not replacing, the existing 2D view).
- Explainable "Why?" panel on influencer/anomaly/community results.
- Hidden-relationship surfacing (path-finder results presented as a named feature, not just a
  utility page).
- Focus Mode (selecting an entity isolates its relevant subgraph + context panel).

**Existing code reused:**
- `app/analytics/centrality.py`, `community.py`, `pathfinder.py`, `anomaly.py` — **zero logic
  changes**; only new read-only endpoints/response shaping on top.
- `frontend/src/components/GraphView.tsx`'s existing props contract (nodes/edges/click
  handler/highlight set) — wrap, don't rewrite, when adding the 3D variant.
- `EntityPanel.tsx` — extends naturally into the "Why?" panel.

**New code required:**
- `react-force-graph-3d`-based `GraphView3D` component sharing `GraphView`'s prop contract.
- A thin `app/api/routes/explain.py` (or extend `analytics.py`) composing existing centrality/
  community/pathfinder output into a structured "reasons" payload per entity.
- Frontend "Why?" UI affordance (expandable panel/drawer).

**Dependencies:** `react-force-graph-3d` (frontend only; same maintainer/API family as the
already-integrated `react-force-graph-2d`, so no new rendering paradigm).

**Acceptance criteria:**
- 3D view renders the same case-scoped graph the 2D view does, with working zoom/rotate/search/
  focus.
- Every influencer and anomaly result has a working "Why?" action that cites concrete graph
  structure and source document IDs — no unexplained scores.
- 2D view remains fully functional for the contexts where it's more appropriate.

---

## Phase 3 — AI Copilot + Hypothesis Lab

**Objective:** Add the natural-language investigative interface, grounded entirely in the existing
graph and analytics — not a general-purpose chatbot.

**Features:**
- AI Investigation Copilot: NL question → routed to an existing endpoint (search / path / centrality
  / community) → narrated, evidence-cited answer.
- Hypothesis Lab: "Could X be a bridge between Network A and Network B?" → orchestrates path-finder
  + betweenness + community + anomaly signals into a supporting/contradicting evidence bundle,
  explicitly framed as an investigative lead, never a verdict.

**Existing code reused:**
- `app/analytics/pathfinder.py`, `centrality.py`, `community.py`, `anomaly.py`, and
  `app/api/routes/entities.py`'s search — the copilot and hypothesis engine call these directly;
  no new analytical logic.

**New code required:**
- `app/services/copilot.py`: an LLM call constrained to tool/function-calling against the existing
  endpoints (not freeform generation).
- `app/api/routes/copilot.py` (chat-style endpoint, case-scoped).
- `app/services/hypothesis.py` + `app/api/routes/hypothesis.py`: the orchestration/evidence-bundle
  logic.
- Frontend: an "AI Insights" nav area with a chat UI + a Hypothesis Lab form/results view.

**Dependencies:** An LLM client SDK (`anthropic` or `openai`, backend only) — a real product
decision (hosted vs. self-hosted) to make explicitly at this phase's start, not silently.

**Acceptance criteria:**
- Every copilot answer traces to at least one concrete API call and cites the entities/evidence it
  used — no unattributed claims.
- A hypothesis run always returns both supporting and (if any) contradicting evidence, never a bare
  yes/no.
- Existing endpoints the copilot calls are untouched and their own tests still pass.

---

## Phase 4 — Evidence Integrity + Tamper-Evident Audit

**Objective:** Directly address the "Blockchain and Cybersecurity" theme, currently the
least-covered area of the whole system.

**Features:**
- Evidence Vault: upload a file, compute SHA-256, store hash + metadata.
- Verification flow: re-hash on demand, compare, return VERIFIED/MISMATCH.
- Migrate the audit log off in-memory storage into a persistent, hash-chained Postgres table (each
  row's hash includes the previous row's hash).

**Existing code reused:**
- `app/services/audit.py`'s `log()`/`list_entries()` call sites — every existing caller
  (`api/routes/auth.py`, `entities.py`, `ingestion.py`) keeps calling the same function signature;
  only the backing store changes.

**New code required:**
- `app/services/evidence.py` (hash, store, verify) + `app/api/routes/evidence.py`.
- File storage (local disk under a case-scoped path is sufficient for a prototype; abstracted behind
  one function so it can move to object storage later).
- Alembic migration for `evidence` and a hash-chained `audit_log` table.
- Frontend: an "Evidence" nav area (upload, list, verify-integrity action).

**Dependencies:** None new — `hashlib` is stdlib. Reuses Phase 1's Postgres/SQLAlchemy setup.

**Acceptance criteria:**
- Every ingest/merge/login/evidence action is durably logged and survives a backend restart.
- Tampering with a stored evidence file's bytes (simulated in a test) is detected as MISMATCH.
- Breaking any historical audit row's content invalidates every subsequent row's chained hash
  (tested directly).

---

## Phase 5 — Timeline + Financial + Geo Intelligence

**Objective:** Build the remaining named PS analytics views, most of which need only a new
presentation layer over data that already exists.

**Features:**
- Timeline Intelligence: chronological view of events/calls/transactions; date-range filtering
  applied to the graph.
- Financial Flow view: filtered subgraph over `FINANCIAL_ACCOUNT`/`TRANSACTED_WITH`, highlighting
  circular/pass-through patterns already detected.
- Communication Intelligence view: frequency/duration visualization over `CALLED` edges.
- Geo Intelligence: map view of `LOCATION` nodes with time-aware filtering.

**Existing code reused:**
- `document_date` already stamped on edges/events (`app/services/pipeline.py`) — the timeline's data
  source.
- `app/analytics/anomaly.py`'s circular-transaction and burst-calling detectors — feed the financial
  and communication views directly.
- `app/graph/schema.py`'s `LOCATION` node type — extend with coordinate attributes, don't replace.

**New code required:**
- `app/api/routes/timeline.py` (chronological aggregation endpoint).
- A date-range query parameter added to `GET /api/graph` and `/api/graph/neighborhood/{id}`.
- Synthetic lat/lng values added to the demo dataset's location records.
- Frontend: Timeline component, Financial Flow view, Geo map component.

**Dependencies:** `maplibre-gl` or `react-leaflet` (frontend, avoids a paid Mapbox token for a
judge-facing demo). No new backend dependencies.

**Acceptance criteria:**
- Filtering the graph by date range returns a correctly reduced node/edge set.
- The Financial Flow view visibly highlights the demo dataset's planted circular transaction.
- The Geo view plots every demo `LOCATION` node at a real coordinate.

---

## Phase 6 — Premium UI/UX

**Objective:** The full visual/IA pass — restructure navigation into the target six areas and apply
a design system worthy of "premium intelligence platform," once the screens it organizes actually
exist.

**Features:**
- Navigation restructured: Overview, Investigations, Network, AI Insights, Evidence, Audit.
- Universal Search bar (frontend composition of the existing `/entities/search` across all types).
- Typography/color/motion design pass across all screens.
- Responsive behavior verified at phone width.

**Existing code reused:** Every screen built in Phases 1–5 — this phase re-skins and re-organizes,
it does not rebuild functionality.

**New code required:** New shared layout/nav components; a small number of shared UI primitives
(buttons, cards, badges) to replace ad hoc Tailwind classes repeated per-page today.

**Dependencies:** None required; `framer-motion` may be pulled forward from Phase 7 if micro-
interactions are wanted here.

**Acceptance criteria:**
- All six nav areas are reachable and populated with real (not placeholder) content.
- No screen breaks below ~400px width.
- Existing functionality (search, ingest, path-find, audit) is reachable and behaves identically
  post-restructure.

---

## Phase 7 — 3D Cinematic Landing + Demo Polish

**Objective:** Build the front door of the demo — deliberately sequenced last so it never displaces
Tier-S functional stability, but finished before judging day since it's the first fifteen seconds of
the pitch.

**Features:**
- 3D scroll-driven landing sequence (fragmented sources → fusion → network → intelligence →
  evidence integrity → platform entry).
- Investigation Replay: animate the demo case's graph/evidence emerging over time.
- Final demo-data walkthrough polish (matching `docs/DEMO_DATA.md`'s narrated story).

**Existing code reused:** The Phase 2 3D graph component's rendering primitives; the demo dataset
and its documented narrative (`docs/DEMO_DATA.md`) as the landing page's actual content, not
placeholder copy.

**New code required:** A new landing route + scroll-driven scene sequence (Three.js/R3F + Framer
Motion); a temporal graph-diff/animation layer for Investigation Replay.

**Dependencies:** `@react-three/fiber`, `@react-three/drei`, `framer-motion`.

**Acceptance criteria:**
- Landing sequence runs at acceptable frame rate on demo hardware.
- Replay accurately reconstructs the order evidence actually entered the graph (sourced from real
  ingestion timestamps, not scripted).
- Landing page never blocks or gates access to the real app for a judge who wants to skip it.

---

## Phase 8 — Testing / Security / Deployment

**Objective:** The hardening pass — close the security gaps identified in Phase 0/the prior audit,
and get the system into a reliably deployable/demoable state.

**Features:**
- Rate limiting on auth and ingestion routes.
- File upload validation (size cap, extension/MIME allowlist) on both CSV/JSON ingestion and
  evidence upload.
- Env-driven CORS configuration (no more hardcoded `localhost:5173`).
- Frontend test coverage (currently zero).
- A full re-walk of every planted demo-data pattern (bridge person, circular flow, burst calls,
  indirect link) to confirm none of it broke across Phases 1–7's changes.

**Existing code reused:** The existing 12-test backend suite as the regression baseline; extend it
rather than replace it.

**New code required:** `slowapi` (or equivalent) rate-limit middleware; upload validation utility;
frontend test setup (Vitest + React Testing Library) and initial test coverage for the highest-risk
screens.

**Dependencies:** `slowapi` (backend), `vitest` + `@testing-library/react` (frontend).

**Acceptance criteria:**
- Login and ingestion routes reject excessive request rates with a clear error, not a crash.
- An oversized or wrong-type upload is rejected with a clear error before touching the pipeline.
- Every demo-data pattern documented in `docs/DEMO_DATA.md` still surfaces correctly end to end.
- CI (or a documented manual checklist) runs backend + frontend tests before any deploy.
