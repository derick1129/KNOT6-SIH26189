# KNOT6 — Component Decision Ledger: KEEP / MODIFY / ADD

> Every existing component of the PRAHARI prototype, mapped to a decision. Read alongside
> [`KNOT6_ARCHITECTURE.md`](KNOT6_ARCHITECTURE.md) (what each of these is today) and
> [`KNOT6_IMPLEMENTATION_ROADMAP.md`](KNOT6_IMPLEMENTATION_ROADMAP.md) (when each change happens).
>
> **Finding: nothing is being REPLACED.** Every working component either stays exactly as-is or is
> extended in place. This is a deliberate outcome of the audit, not an oversight — see each table's
> "why" column.

## KEEP — unchanged, as-is

| Component | Path | Why it stays untouched |
|---|---|---|
| Dual-backend graph store | `app/db/graph_store.py` | Already the NetworkX-demo / Neo4j-production seam KNOT6 needs; every analytics/API call site depends only on the `GraphStore` interface. |
| NLP extraction baseline | `app/nlp/entity_extraction.py`, `patterns.py` | Runs with no GPU/training data; correct default for a prototype. Upgrade path (fine-tuned/LLM extractor) is additive later, not urgent for Phase 0–5. |
| Entity resolution engine | `app/resolution/entity_resolution.py` | Already implements "show confidence + reasons, never silently merge." Verified live this phase (auto-merge only ≥97%, everything else surfaced as a candidate). |
| Centrality / community / anomaly / pathfinder | `app/analytics/*.py` | Verified live this phase against the real demo dataset — correct, explainable output. Every later phase (Intelligence Core, Copilot, Hypothesis Lab) composes these, never replaces them. |
| Ingestion loaders | `app/ingestion/loaders.py` | CDR/financial/criminal-history loaders work correctly; Phase 1 adds a `case_id` parameter but the loading logic itself is untouched. |
| Graph schema vocabulary | `app/graph/schema.py` | Node/relation types substantially match the spec already; Phase 1 *adds* `EVIDENCE` and wires up the already-declared `CASE` type rather than redesigning the schema. |
| Demo dataset | `backend/data/demo/` | Already contains a bridge person, community clusters, an indirect relationship, a circular money loop, and a burst-calling pattern. Verified live this phase. |
| Backend test suite | `backend/tests/` | 11/12 passing, verified this phase. Extended, not replaced, as new modules land. |
| JWT auth mechanics | `app/core/security.py` | Token issue/verify logic is correct and stays; only the *user directory* backing it changes (see MODIFY). |
| React app shell, routing, typed API client | `frontend/src/App.tsx`, `api/client.ts` | Correct pattern (typed responses mirroring Pydantic schemas); extended with new routes/types, not rebuilt. |
| 2D Graph view | `frontend/src/components/GraphView.tsx` | Stays as the 2D mode alongside the new 3D mode (Phase 2) — valid for contexts where 2D is clearer, per product direction. |
| Docker Compose / dual run-mode setup | `docker-compose.yml`, `README.md`'s two quick-starts | Correct shape for a demo-vs-production story; unchanged. |

## MODIFY — same component, extended or adjusted

| Component | Path | What changes | Phase |
|---|---|---|---|
| Graph schema | `app/graph/schema.py` | Add `EVIDENCE` node type; reconcile `MET_AT` into `ALL_RELATION_TYPES`; add `case_id` tagging | 1 |
| Auth / RBAC | `app/core/security.py`, `api/deps.py` | Add Viewer role; add case-membership check alongside role check | 1 |
| Audit log | `app/services/audit.py` | Same `log()`/`list_entries()` call sites, new persistent + hash-chained backing store | 4 |
| Ingestion routes | `app/api/routes/ingestion.py` | Require a `case_id`; loader logic itself unchanged | 1 |
| `Neo4jGraphStore.record_edge_event` | `app/db/graph_store.py` | Move from aggregate/last-event to a real per-event model, matching the NetworkX backend's fidelity | later (not yet scheduled — flagged in architecture doc §6) |
| Frontend navigation | `frontend/src/components/Sidebar.tsx`, `App.tsx` | Restructure 5 routes into 6 target nav areas | 6 |
| Visual design tokens | `tailwind.config.js`, `styles/index.css` | New palette/typography pass; Tailwind itself stays | 6 |
| `requirements.txt` pins | `backend/requirements.txt` | Several packages need version bumps for Python 3.14 wheel compatibility (see `KNOT6_ARCHITECTURE.md` §7) — a deliberate decision for whoever owns Phase 1, not done silently in Phase 0 | 1 (proposed) |

## ADD — genuinely new construction

| Component | Why it's net-new | Phase | Reuse leverage |
|---|---|---|---|
| PostgreSQL layer (users, cases, evidence, audit) | Nothing persists today outside the graph | 1 | None — new infrastructure |
| Investigation/case workspace | No case concept exists anywhere in the current code | 1 | Low — new UI + new scoping logic throughout |
| 3D Network Explorer | Zero 3D dependencies in `package.json`, confirmed by inspection | 2 | High — wraps existing `GraphView` contract |
| Explainability "Why?" layer | No UI affordance exists; underlying data mostly already computed | 2 | High — composes existing analytics output |
| AI Investigation Copilot | No NL interface exists | 3 | High — routes to existing endpoints, doesn't reinvent analysis |
| Hypothesis Lab | Named feature doesn't exist | 3 | High — orchestrates existing pathfinder/centrality/community/anomaly modules |
| Evidence Vault + hash verification | No file storage or hashing exists anywhere | 4 | None — new subsystem |
| Tamper-evident audit chain | Current audit log has zero integrity guarantee | 4 | Medium — reuses existing audit call sites, new storage |
| Timeline Intelligence view | Timestamps exist in data; no aggregation endpoint or UI | 5 | Medium |
| Geo Intelligence view | `LOCATION` nodes have no coordinates; no map UI | 5 | Low |
| 3D scroll-driven landing page | No landing page exists at all today (app opens straight to `/login`) | 7 | Low — pure new build |
| Investigation Replay | No temporal animation layer exists | 7 | Low |
| Universal Search bar | `/entities/search` exists; no unified entry-point UI | 6 | High — frontend composition only |
| Rate limiting, upload validation | Absent entirely today | 8 | None |
| Frontend test suite | Zero frontend tests exist today (backend has 12) | 8 | None |
