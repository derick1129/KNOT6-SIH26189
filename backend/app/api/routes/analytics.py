from __future__ import annotations

from fastapi import APIRouter, Depends

from app.analytics.anomaly import run_all_detectors
from app.analytics.centrality import compute_influencers
from app.analytics.community import compute_communities
from app.api.deps import get_store, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore
from app.graph import schema
from app.models.schemas import AnomalyFlag, Community, DashboardSummary, InfluencerScore

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/influencers", response_model=list[InfluencerScore])
def get_influencers(top_n: int = 10,
                     user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                     store: GraphStore = Depends(get_store)):
    return compute_influencers(store, top_n=top_n)


@router.get("/communities", response_model=list[Community])
def get_communities(user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                     store: GraphStore = Depends(get_store)):
    return compute_communities(store)


@router.get("/anomalies", response_model=list[AnomalyFlag])
def get_anomalies(user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                   store: GraphStore = Depends(get_store)):
    return run_all_detectors(store)


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                   store: GraphStore = Depends(get_store)):
    nodes = store.all_nodes()
    edges = store.all_edges()
    influencers = compute_influencers(store, top_n=5)
    communities = compute_communities(store)
    anomalies = run_all_detectors(store)

    return DashboardSummary(
        total_entities=len(nodes),
        total_relations=len(edges),
        total_persons=sum(1 for n in nodes if n.type == schema.PERSON),
        total_cases=sum(1 for n in nodes if n.type == schema.CASE),
        top_influencers=influencers,
        community_count=len(communities),
        open_anomalies=len(anomalies),
        recent_anomalies=anomalies[:8],
    )
