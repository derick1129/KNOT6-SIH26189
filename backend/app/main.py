import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analytics, audit, auth, cases, copilot, entities, evidence, graph, hypotheses, ingestion, integrity,
    investigations,
)
from app.core.config import get_settings
from app.core.security import ensure_demo_users
from app.db.graph_store import ScopedGraphStore, get_graph_store
from app.db.models import Investigation, Case
from app.db.postgres import SessionLocal, init_db

settings = get_settings()
logger = logging.getLogger("prahari")

app = FastAPI(
    title=settings.app_name,
    description=(
        "Prototype for SIH Problem Statement 26189 (Ministry of Home Affairs / NCRB) -- "
        "ingests FIRs, CDRs, financial records, surveillance/social-media intelligence and "
        "criminal-history data, extracts entities and relationships, builds a unified "
        "knowledge graph, and surfaces key influencers, communities and suspicious patterns."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(investigations.router, prefix=settings.api_prefix)
app.include_router(cases.router, prefix=settings.api_prefix)
app.include_router(evidence.router, prefix=settings.api_prefix)
app.include_router(copilot.router, prefix=settings.api_prefix)
app.include_router(ingestion.router, prefix=settings.api_prefix)
app.include_router(entities.router, prefix=settings.api_prefix)
app.include_router(graph.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(integrity.router, prefix=settings.api_prefix)
app.include_router(hypotheses.router, prefix=settings.api_prefix)

DEMO_INVESTIGATION_NAME = "Operation Nexus"
DEMO_CASE_NUMBER = "CASE-001"


@app.on_event("startup")
def _init_postgres() -> None:
    # Safety net for the zero-infra/SQLite dev path -- idempotent, no-op if
    # tables already exist. The reviewable, versioned path for real
    # PostgreSQL deployments is the Alembic migration in
    # backend/alembic/versions/ (see docs/KNOT6_ARCHITECTURE.md).
    init_db()
    db = SessionLocal()
    try:
        ensure_demo_users(db)
    finally:
        db.close()


@app.on_event("startup")
def _seed_on_startup() -> None:
    if not settings.auto_seed_demo:
        return

    db = SessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.name == DEMO_INVESTIGATION_NAME).first()
        if investigation is None:
            investigation = Investigation(
                name=DEMO_INVESTIGATION_NAME,
                description=(
                    "Synthetic demo investigation (see docs/DEMO_DATA.md) bundled so the app is "
                    "immediately explorable without uploading files first."
                ),
                created_by="admin",
                is_demo_seed=True,
            )
            db.add(investigation)
            db.commit()
            db.refresh(investigation)
        elif not investigation.is_demo_seed:
            # Backfill for a database created before `is_demo_seed` existed
            # (see the a7f3c9e21b04 migration's equivalent backfill for the
            # Postgres/Docker path) -- the zero-infra SQLite path only runs
            # `create_all`, which never adds columns to an existing table's
            # data, so this is the corresponding fix-up for it.
            investigation.is_demo_seed = True
            db.commit()

        case = db.query(Case).filter(Case.case_number == DEMO_CASE_NUMBER).first()
        if case is None:
            case = Case(
                investigation_id=investigation.id,
                case_number=DEMO_CASE_NUMBER,
                title="Organized Network Analysis",
                description="One small fictional syndicate, run through the real pipeline -- see docs/DEMO_DATA.md.",
                priority="HIGH",
                created_by="admin",
            )
            db.add(case)
            db.commit()

        store = ScopedGraphStore(get_graph_store(), investigation.id)
        if store.all_nodes():
            return

        from app.services.seed_demo import seed
        try:
            summary = seed(store)  # unmodified seed_demo.py -- works unchanged against any GraphStore
            logger.info("Seeded demo dataset into investigation %s: %s", investigation.id, summary)
        except Exception:
            logger.exception("Demo data seeding failed; starting with an empty graph.")
    finally:
        db.close()


@app.on_event("startup")
def _rebuild_investigation_graphs_on_startup() -> None:
    """
    Graph-durability fix (see app/services/graph_recovery.py's docstring):
    the GraphStore never survives a process restart on its own, unlike the
    PostgreSQL-backed Investigation/Case/Evidence rows sitting right next to
    it. Runs after `_seed_on_startup` so it only ever looks at *non-demo*
    investigations -- the demo dataset already has its own from-canonical-
    source restore path and must never have Evidence rows once
    `ensure_not_demo_protected` is in place.
    """
    db = SessionLocal()
    try:
        from app.services.graph_recovery import rebuild_missing_investigation_graphs
        rebuilt = rebuild_missing_investigation_graphs(db)
        if rebuilt:
            logger.info("Rebuilt %d investigation graph(s) from persisted evidence on startup.", len(rebuilt))
    except Exception:
        logger.exception("Investigation graph rebuild failed; some investigations may show an empty graph.")
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "status": "ok",
        "graph_backend": settings.graph_backend,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
