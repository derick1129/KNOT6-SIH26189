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


@lru_cache
def get_settings() -> Settings:
    return Settings()
