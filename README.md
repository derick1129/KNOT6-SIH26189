# PRAHARI — AI-Powered Criminal Network Analysis System

A working prototype for **SIH Problem Statement 26189** (Ministry of Home Affairs / National Crime
Records Bureau, Women Safety Division): an AI system that ingests fragmented crime data — FIRs, Call
Detail Records, financial transactions, surveillance reports, social-media intelligence, and criminal
history databases — extracts entities and relationships, builds a unified knowledge graph, and surfaces
key influencers, likely gangs/cells, and suspicious patterns for investigators.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the detailed research, design rationale, and
development roadmap. See **[docs/DEMO_DATA.md](docs/DEMO_DATA.md)** for a guided walkthrough of the
bundled synthetic dataset and what each analytics module finds in it.

## Why it runs two ways

| Mode | Command | What you get |
|---|---|---|
| **Zero-infra demo** | `uvicorn app.main:app` (see below) | Everything in-process. No Docker, no database server. This is the default and how a judge/reviewer should first run it. |
| **Production-shaped** | `docker compose up` | Real Neo4j 5.x backend with the Graph Data Science plugin — the architecture intended for an actual pilot deployment at scale. |

Both modes run the *exact same* application code (`app/db/graph_store.py` is the only seam that
changes) — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#graph-backend) for why.

## Quick start (zero-infra demo)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn app.main:app --reload --port 8000
```

The API auto-seeds a synthetic demo dataset (a small fictional syndicate) on first startup, so
`http://localhost:8000/docs` is immediately explorable. Set `AUTO_SEED_DEMO=false` to start empty.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and sign in with one of the demo accounts shown on the login screen
(`investigator` / `investigator123` is the fastest path in).

## Quick start (production-shaped, Docker)

```bash
docker compose up --build
```

This starts Neo4j (with APOC + GDS plugins), the backend pointed at it (`GRAPH_BACKEND=neo4j`), and the
frontend. Neo4j Browser is at `http://localhost:7474`.

## Running the tests

```bash
cd backend
pytest -q
```

12 tests cover entity extraction (spaCy + regex), entity resolution (fuzzy merge logic), and every
analytics module (centrality, community detection, anomaly detection, path finding) — see
`backend/tests/`. All pass against the zero-infra `NetworkXGraphStore`, so they need no external
services.

You can also run the whole ingestion → NLP → graph → analytics pipeline standalone, without the API:

```bash
python backend/scripts/seed_demo.py
```

## Project layout

```
backend/
  app/
    core/         config, JWT auth
    db/           graph_store.py — the NetworkX / Neo4j abstraction
    nlp/          entity + relation extraction (spaCy + regex)
    resolution/   fuzzy entity de-duplication
    graph/        schema + graph-building
    ingestion/    CDR / financial / criminal-history CSV loaders
    analytics/    centrality, community detection, anomaly detection, path finding
    services/     pipeline orchestration, audit log, demo-data seeding
    api/routes/   FastAPI endpoints
  data/demo/       synthetic demo dataset
  scripts/         seed_demo.py CLI
  tests/
frontend/
  src/
    pages/         Dashboard, Graph Explorer, Path Finder, Ingest Data, Audit Log
    components/    GraphView (force-directed graph), EntityPanel, Sidebar, StatCard
    api/           typed API client
    store/         auth context
docs/
  ARCHITECTURE.md  detailed research, design rationale, and roadmap
  DEMO_DATA.md     guided walkthrough of the bundled dataset
docker-compose.yml
```

## Roles (demo accounts)

| Role | Username | Password | Can do |
|---|---|---|---|
| Admin | `admin` | `admin123` | Everything, incl. audit log |
| Investigator | `investigator` | `investigator123` | Ingest data, explore graph, run analytics |
| Analyst | `analyst` | `analyst123` | Same as investigator, plus entity-resolution merge review |

## Known limitations (prototype scope — see ARCHITECTURE.md §9 for the path to production)

- NLP extraction uses spaCy's small English model plus rule-based relation extraction — good recall on
  the demo dataset, but will mis-tag some entities (e.g. occasionally tagging a person as an
  organization) the way any general-purpose small NER model does. Production deployment should
  fine-tune on labelled Indian crime-report text (see ARCHITECTURE.md §9.1).
- The audit log and JWT user directory are in-memory for this prototype; production needs a persistent,
  tamper-evident store and integration with the agency's real identity provider (§9.4, §9.5).
- Anomaly detectors are explainable heuristics tuned for a demo dataset, not a trained model — see
  §9.2 for the intended evolution once real, labelled case outcomes exist to validate against.
