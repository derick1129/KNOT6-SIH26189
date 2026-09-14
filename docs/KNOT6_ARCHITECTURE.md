# KNOT6 — Current Architecture (as of Phase 1)

> **Scope of this document:** what exists and runs today, verified directly on 2026-09-11. It
> describes the system as it actually is, not as KNOT6 intends it to become — see
> [`KNOT6_IMPLEMENTATION_ROADMAP.md`](KNOT6_IMPLEMENTATION_ROADMAP.md) for what's planned, and
> [`KNOT6_KEEP_MODIFY_ADD.md`](KNOT6_KEEP_MODIFY_ADD.md) for the per-component reuse decision.
> Phase 0's original findings are preserved below, updated in place where Phase 1 changed them.

## 0. Product identity

The project is officially **KNOT6**. The codebase was originally built under an earlier working
name, **PRAHARI**, and an earlier specification referred to the product as **NETRA**. Both names
still appear throughout the existing code, UI strings, and documentation (`README.md`, the FastAPI
app title in `backend/app/main.py`, the sidebar logo in `frontend/src/components/Sidebar.tsx`, the
login screen, etc.) — this document leaves that branding untouched, as instructed. Renaming
strings to KNOT6 is a deliberate, later task, not a Phase 0/1 action.

## 1. The architectural transition Phase 1 made

```
BEFORE (Phase 0)                          AFTER (Phase 1)
─────────────────                         ───────────────
one flat, global graph                    users
  + in-memory audit log                     → investigations
  + in-memory user dict                       → cases
                                                 → evidence (metadata + storage ref)
                                                   → extracted entities/relationships
                                                     → investigation-scoped graph
                                                       → analytics/findings
                                          + persistent audit trail (PostgreSQL)
```

This was implemented as **one new class** (`ScopedGraphStore`, §5) sitting above the existing
`GraphStore` implementations, plus a new PostgreSQL-backed metadata layer (§3) alongside — not
inside — the graph. Nothing in `app/nlp/`, `app/resolution/`, or `app/analytics/` changed at all;
see [`KNOT6_KEEP_MODIFY_ADD.md`](KNOT6_KEEP_MODIFY_ADD.md) for the full reuse accounting.

## 2. What actually runs, verified this phase

Two run modes, both exercising the same application code, each now with two independently-swappable
backends:

| Concern | Zero-infra default | Docker/production |
|---|---|---|
| Graph | `GRAPH_BACKEND=networkx` (in-process) | `GRAPH_BACKEND=neo4j` |
| Application DB | `DATABASE_URL=sqlite:///./knot6_dev.db` | `DATABASE_URL=postgresql+psycopg://...` (docker-compose's `postgres` service) |

Live verification performed this phase (backend on `NetworkXGraphStore` + SQLite, port 8000):

- Login persists and works for all **four** demo accounts (admin/investigator/analyst/**viewer**,
  the PS's full role vocabulary) after a backend restart — proving `users` now survives in
  PostgreSQL, not an in-memory dict.
- The demo investigation (**"Operation Nexus"**, case **CASE-001 — Organized Network Analysis**) is
  created idempotently on startup and the bundled synthetic dataset seeds *into it* — **59
  entities, 102 relations**, same numbers as Phase 0, now investigation-scoped instead of global.
- `GET /api/graph?investigation_id=<demo>` returns clean, unprefixed entity IDs (e.g.
  `person_c7df0c25057b`) — confirming `ScopedGraphStore` correctly unscopes at the API boundary.
- **Isolation, directly tested**: a brand-new investigation's graph is empty (`0` nodes) even
  though the demo investigation has 59; two investigations each given different evidence never see
  each other's extracted entities (see `backend/tests/test_phase1_investigations.py`).
- Evidence upload → the **unmodified** ingestion pipeline → graph, end to end: uploading a `.txt`
  file as `FIR` evidence under a case extracted entities/relations and landed them in that
  investigation's scoped graph, with `Evidence.processing_status` moving
  `UPLOADED → PROCESSING → PROCESSED`.
- RBAC enforced server-side: `viewer` gets `403` on every write route (create investigation, create
  case, upload evidence) and `200` on every read route.
- `/api/analytics/dashboard` still ranks **Suresh Yadav** above **Vikram Rathore** by composite
  centrality in the scoped demo graph — the analytics engine's output is byte-for-byte what Phase 0
  verified, now reached through a different (scoped) path.
- Frontend builds cleanly (`tsc -b && vite build`, zero errors); the new Investigations → Case →
  Evidence screens compile and route correctly alongside the five pre-existing screens, all now
  investigation-aware (see §4).
- Database migration verified from a clean database: `alembic upgrade head` → 6 tables created;
  `alembic downgrade base` → all dropped cleanly; `upgrade head` again → clean re-create. Verified
  against SQLite (see §8 — no PostgreSQL server was reachable in this sandboxed dev environment;
  the schema uses only portable column types for exactly this reason).
- Full backend test suite: **31 passed**, 1 failed (the same pre-existing, documented
  spaCy-model-version test from Phase 0 — untouched, not hidden). 12 original tests (11 pass + the
  1 documented failure) + 20 new Phase 1 tests, all passing.

## 3. PostgreSQL: application/business metadata (new this phase)

`app/db/models.py` (SQLAlchemy 2.0 declarative), `app/db/postgres.py` (engine/session),
`backend/alembic/` (migrations). Deliberately **never** stores the graph itself — see §5.

| Table | Purpose |
|---|---|
| `users` | Replaces the in-memory demo-user dict; same 3 accounts plus `viewer` (4th role). |
| `investigations` | Top of the hierarchy: id, name, description, status (ACTIVE/ARCHIVED/CLOSED), created_by/at/updated_at. |
| `cases` | Belongs to one investigation; case_number (unique), title, status (OPEN/UNDER_REVIEW/CLOSED/ARCHIVED), priority (LOW/MEDIUM/HIGH/CRITICAL). |
| `evidence` | Belongs to one case; filename/original_filename/source_type/mime_type/file_size/storage_path/processing_status/processing_summary. **Metadata + a storage reference only — never file bytes** (see §6). |
| `audit_entries` | Replaces the in-memory audit list; same `log()`/`list_entries()` call signature everywhere, now durable. Hash-chaining (tamper-evidence) is Phase 4, not yet built. |
| `entity_resolution_decisions` | New: records an analyst's accept/reject on a merge candidate, so a rejected pair doesn't keep resurfacing. Schema only this phase — not yet wired into `resolve_candidates()`. |

Column types are deliberately portable (`String`/`Text`/`DateTime`/`JSON`, no Postgres-only types)
so the identical model code and Alembic migration apply to both SQLite (zero-infra dev) and
PostgreSQL (Docker/production) — mirroring the same "one interface, two backends" philosophy
`GraphStore` already established for the graph.

**Deliberately not built this phase** (see `KNOT6_KEEP_MODIFY_ADD.md`'s ADD table for why each is
out of scope, not forgotten): a `findings` table, an `investigation_configuration` table, and
per-case membership ACLs (authorization in Phase 1 is role-based, matching the existing RBAC
pattern — not yet scoped per case-membership).

## 4. Frontend module map (updated this phase)

| Layer | Path | Responsibility |
|---|---|---|
| Entry | `src/main.tsx`, `src/App.tsx` | Router + `AuthProvider` + **`InvestigationProvider`** (new), 8 protected routes + `/login` |
| API client | `src/api/client.ts` | Typed axios wrapper + **`Investigation`/`Case`/`EvidenceItem`** types (new) |
| Auth store | `src/store/auth.tsx` | Unchanged |
| **Investigation store** | **`src/store/investigation.tsx`** (new) | Which investigation the rest of the app is scoped to; defaults to the first (demo) investigation |
| Pages | `src/pages/*.tsx` | Dashboard, GraphExplorer, PathFinder, Ingestion, AuditLog, Login (all pre-existing, now investigation-aware) + **`Investigations`, `InvestigationDetail`, `CaseDetail`** (new) |
| Components | `src/components/*.tsx` | Unchanged (`GraphView`, `EntityPanel`, `Sidebar` — Sidebar gained an "Investigations" nav link + active-investigation indicator, `StatCard`) |

Every pre-existing screen (Dashboard, Graph Explorer, Path Finder, Ingest Data) now reads
`useInvestigation().currentId` and passes it as `investigation_id` on every relevant API call, so
the demo experience is consistently scoped to "Operation Nexus" rather than mixing scoped and
unscoped views. This was necessary, not optional — see §7's note on why an unscoped view now shows
namespaced IDs. No 3D library, animation library, or map/chart library was added — still explicitly
out of scope until Phase 2/5/7.

## 5. `ScopedGraphStore`: investigation isolation without touching the graph engine

`app/db/graph_store.py` — one new class, zero changes to `GraphStore`, `NetworkXGraphStore`, or
`Neo4jGraphStore`. Every node ID it writes is transparently namespaced
(`inv_<investigation_id>::<logical_id>`) before reaching the wrapped store, and stripped back to
the plain logical ID on every read — so `app/graph/graph_builder.py`,
`app/resolution/entity_resolution.py`, `app/analytics/*.py`, and `app/services/pipeline.py` needed
**zero code changes**: they're simply handed a `ScopedGraphStore(get_graph_store(), investigation_id)`
instead of the raw store at the API layer (`app/api/deps.py:get_store_for`).

Because nothing ever creates an edge between two different investigations' namespaced IDs,
isolation falls directly out of the ID namespacing — `neighbors()`/path-finding naturally never
traverses out of scope, with no extra filtering logic layered on top of every read. `case_id` is
deliberately *not* part of the graph-level scope (see the class docstring): the isolation boundary
that matters is the investigation; entities legitimately recur across cases within one
investigation.

## 6. File storage abstraction (new this phase)

`app/services/storage.py` — a small `Storage` protocol (`save`/`read`) with one implementation,
`LocalFileStorage`, writing under `EVIDENCE_STORAGE_DIR` (default `./data/evidence`), namespaced by
investigation. PostgreSQL's `evidence.storage_path` holds only the reference this returns, never
file bytes. SHA-256 hashing and tamper-evident verification are explicitly Phase 4 — nothing here
computes a hash yet.

## 7. Pipeline (current, real) — now investigation-scoped

```
FIR / CDR / financial / criminal-history / social-media
        │
        ▼  (new: registered as Evidence metadata first, or ingested directly as before)
  backend/app/ingestion/loaders.py        (CDR, financial, criminal-history CSV)
  backend/app/nlp/entity_extraction.py    (FIR, surveillance, social, intel text)
        │                                  ── UNCHANGED from Phase 0 ──
        ▼
  backend/app/graph/graph_builder.py      (mint node IDs, write to GraphStore)
        │
        ▼
  backend/app/resolution/entity_resolution.py   (fuzzy name merge + shared-neighbor corroboration)
        │
        ▼
  backend/app/db/graph_store.py           (ScopedGraphStore → NetworkXGraphStore/Neo4jGraphStore)
        │
        ▼
  backend/app/analytics/*.py              (centrality, community, anomaly, pathfinder — UNCHANGED)
        │
        ▼
  backend/app/api/routes/*.py             (FastAPI, JWT + RBAC gated, now investigation-aware)
        │
        ▼
  frontend/src/pages/*.tsx                (React, 2D force-directed graph, investigation-scoped)
```

**Two ingestion entry points now exist, both reusing the identical, unmodified
`ingest_text_document`/`ingest_structured` functions in `app/services/pipeline.py`:**
`POST /api/ingest/*` (pre-existing, now accepts an *optional* `investigation_id` — omitted preserves
exact Phase-0 behavior) and `POST /api/investigations/{id}/cases/{id}/evidence` (new: registers
Evidence metadata in PostgreSQL, then runs the same pipeline scoped to that investigation).

**A real gap found and fixed this phase:** the moment any data is written through a
`ScopedGraphStore` (which is now true of the auto-seeded demo dataset), the *raw, unscoped* view of
that same underlying store exposes the physical, namespaced IDs (`inv_<id>::person_...`) — not a
crash, but a broken-looking ID contract for any caller that doesn't pass `investigation_id`. Fixed
by making every existing frontend screen investigation-aware (§4) rather than leaving a
half-migrated default view; documented here because it's exactly the kind of interaction a
"backward-compatible extension" can hide until it's actually exercised.

## 8. Data model (current)

**Node types** (`app/graph/schema.py`): `PERSON`, `PHONE`, `VEHICLE`, `LOCATION`, `ORGANIZATION`,
`FINANCIAL_ACCOUNT`, `EVENT`, `CASE`. Still unchanged from Phase 0 — `CASE` (the graph node type) is
still not created by any loader; **case** as a first-class concept now lives in PostgreSQL instead
(§3), which is where the PS's case-management need actually maps. `EVIDENCE` as a graph node type
was *not* added this phase (evidence is PostgreSQL metadata + a storage reference, not a graph
entity) — revisit only if a future phase needs evidence-to-entity graph edges specifically.

**Relation types**: unchanged from Phase 0, including the still-unreconciled `MET_AT` vs.
`ALL_RELATION_TYPES` inconsistency noted then (still harmless, still not fixed — no phase has needed
to touch `schema.py`'s relation list yet).

## 9. Storage reality (updated)

| What | Where it lives now |
|---|---|
| Graph (entities/relations) | In-process (`NetworkXGraphStore`) or Neo4j, namespaced per investigation by `ScopedGraphStore` |
| Users | **PostgreSQL** (`users` table) — persists across restarts, verified |
| Investigations, cases, evidence metadata | **PostgreSQL** — persists across restarts, verified |
| Audit log | **PostgreSQL** (`audit_entries`) — persists across restarts, verified. Not yet tamper-evident (Phase 4). |
| Evidence file bytes | Local filesystem (`EVIDENCE_STORAGE_DIR`) — not yet hashed/verified (Phase 4) |

`docker-compose.yml` now starts **postgres + neo4j + backend + frontend** but — same honest caveat
as Phase 0 — **no Docker run was performed this phase either** (no Docker available in this dev
environment; see §11). The `Neo4jGraphStore.record_edge_event` fidelity gap noted in Phase 0 is
unchanged and still applies identically once `ScopedGraphStore` wraps a `Neo4jGraphStore`.

## 10. Runtime environment notes (Phase 0, still accurate + new Phase 1 findings)

Same Python 3.14 environment as Phase 0 (§ below unchanged from that phase's findings), with one
**new** compatibility issue found this phase, because Phase 1 was the first time the password
hash/verify path was actually *exercised* (Phase 0's login checked a plaintext dict; it never called
`pwd_context.hash()`/`.verify()` even though `passlib[bcrypt]` was already a listed dependency):

| Package | requirements.txt today | Installed / pinned |
|---|---|---|
| `pydantic` | 2.13.5 | (Phase 0 finding, now applied to requirements.txt) |
| `spacy` | 3.8.16 | (Phase 0 finding, now applied) |
| `rapidfuzz` | 3.14.1 | (Phase 0 finding, now applied) |
| `scipy` | 1.16.1 | (Phase 0 finding, now applied) |
| `bcrypt` | **4.0.1 (new, pinned below 4.1)** | passlib 1.7.4 (unmaintained since 2020) probes a `bcrypt.__about__` attribute removed in bcrypt≥4.1, raising a confusing `"password cannot be longer than 72 bytes"` error on hash/verify. Pinning `bcrypt==4.0.1` (last version compatible with passlib 1.7.4's internal checks) fixes it outright. |
| `pandas` | **removed** | Confirmed unused by any application code in Phase 0; dropped while already touching this file rather than carried forward as dead weight. |

Unlike Phase 0 (which deliberately left `requirements.txt` untouched and only recorded findings),
**Phase 1 applied all of the above to `requirements.txt` directly**, plus the new
`sqlalchemy`/`alembic`/`psycopg[binary]` dependencies — this was unavoidable: Phase 1's own code
(the Postgres layer) needs them to run at all, so "don't touch requirements.txt" was no longer an
option once real persistence was the task.

## 11. Honest current limitations

- No PostgreSQL server was available in this sandboxed dev environment (no Docker, no local
  install) — every verification in §2 ran against SQLite. The schema and Alembic migration use only
  portable types specifically so this is low-risk, but genuine PostgreSQL verification (real
  concurrent connections, `psycopg` wire behavior, Docker networking) has not happened yet.
- `entity_resolution_decisions` exists as a table but isn't wired into
  `resolve_candidates()`/the resolution API yet — schema only, deliberately deferred (see
  `KNOT6_KEEP_MODIFY_ADD.md`).
- Per-case authorization (a user must be a *member* of a case) was not built — Phase 1 authorization
  is role-based only, matching the pre-existing RBAC pattern; anyone with `investigator`/`analyst`/
  `admin` can act on any investigation. Explicit product decision, not an oversight — see
  `KNOT6_KEEP_MODIFY_ADD.md`.
- Evidence integrity (hashing/verification) is entirely absent — Phase 4 scope, untouched.
- No 3D visualization, no AI copilot, no hypothesis lab, no timeline/geo view — unchanged from
  Phase 0, still future phases.
- The same spaCy-model-version test failure from Phase 0 remains, untouched and undisguised (see
  §2's test count).
