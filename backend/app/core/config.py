"""
Central configuration for PRAHARI.

Everything is overridable via environment variables / .env so the same
codebase runs three ways:

1. Zero-infra demo  -> GRAPH_BACKEND=networkx (default). Pure in-process
   graph, nothing to install, nothing to run. This is how the SIH demo runs.
2. Real deployment  -> GRAPH_BACKEND=neo4j, pointed at a Neo4j 5.x instance
   (with the Graph Data Science plugin for production-grade centrality /
   community detection at scale).
3. Tests            -> GRAPH_BACKEND=networkx, isolated per test.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PRAHARI - AI-Powered Criminal Network Analysis System"
    api_prefix: str = "/api"

    # --- Graph backend -----------------------------------------------
    graph_backend: str = "networkx"  # "networkx" | "neo4j"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # --- Application database (KNOT6 Phase 1) ---------------------------
    # Users, investigations, cases, evidence metadata, audit history and
    # entity-resolution review state live here -- NEVER the graph itself
    # (that stays in NetworkX/Neo4j via GraphStore). Mirrors the same
    # zero-infra-default / Docker-overrides-to-real-service pattern already
    # used for graph_backend above: docker-compose points this at the real
    # `postgres` service; a bare `uvicorn app.main:app` run defaults to a
    # local SQLite file so the zero-infra demo story still needs nothing
    # installed. See docs/KNOT6_ARCHITECTURE.md.
    database_url: str = "sqlite:///./knot6_dev.db"

    # --- Evidence storage (KNOT6 Phase 1) --------------------------------
    # Local filesystem for the prototype; see app/services/storage.py for
    # the abstraction that makes this swappable for object storage later.
    evidence_storage_dir: str = "./data/evidence"

    # --- Auth ----------------------------------------------------------
    jwt_secret: str = "change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480

    # --- Entity resolution thresholds ----------------------------------
    name_match_threshold: int = 88  # rapidfuzz token_sort_ratio, 0-100

    # --- Anomaly detection tunables -------------------------------------
    burst_call_window_hours: int = 48
    burst_call_min_count: int = 5
    short_call_max_seconds: int = 20
    circular_txn_max_hops: int = 5

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Seed the bundled synthetic demo dataset on startup so the app is
    # immediately explorable. Set to false for a clean/empty graph
    # (e.g. before ingesting real case data).
    auto_seed_demo: bool = True

    # --- Case Intelligence / AI Copilot (grounded, provider-abstracted) ----
    # Deliberately optional: the deterministic Case Intelligence summary and
    # investigation-scoped search (app/services/investigation_intelligence.py,
    # investigation_search.py) never depend on these and work with none of
    # this configured. Only POST /investigations/{id}/copilot needs an LLM
    # provider; when anthropic_api_key is unset, app/copilot/llm_provider.py
    # returns a provider whose `available` is False and the copilot endpoint
    # answers with a clear "not configured" state instead of faking a reply.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_base_url: str = "https://api.anthropic.com"

    # Generic, provider-agnostic aliases (LLM_PROVIDER / LLM_API_KEY /
    # LLM_MODEL) -- app/copilot/llm_provider.py prefers these when set, and
    # falls back to the ANTHROPIC_* settings above otherwise, so existing
    # deployments/`.env` files keep working unchanged. "anthropic" is the
    # only provider actually implemented today; this just avoids hardcoding
    # the *configuration surface* to one vendor's env var names, matching
    # the LLMProvider abstraction that already supports adding another.
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
