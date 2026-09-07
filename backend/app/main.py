import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, audit, auth, entities, graph, ingestion
from app.core.config import get_settings
from app.db.graph_store import get_graph_store

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
app.include_router(ingestion.router, prefix=settings.api_prefix)
app.include_router(entities.router, prefix=settings.api_prefix)
app.include_router(graph.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)


@app.on_event("startup")
def _seed_on_startup() -> None:
    if not settings.auto_seed_demo:
        return
    store = get_graph_store()
    if store.all_nodes():
        return
    from app.services.seed_demo import seed
    try:
        summary = seed(store)
        logger.info("Seeded demo dataset: %s", summary)
    except Exception:
        logger.exception("Demo data seeding failed; starting with an empty graph.")


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
