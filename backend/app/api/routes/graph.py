from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_store, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore
from app.models.schemas import EntityOut, GraphOut, PathResult, RelationOut
from app.analytics.pathfinder import find_path

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphOut)
def get_full_graph(user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                    store: GraphStore = Depends(get_store)):
    nodes = [EntityOut(id=n.id, type=n.type, label=n.label, attributes=n.attributes,
                        source_count=len(n.source_documents)) for n in store.all_nodes()]
    edges = [RelationOut(id=e.id, source=e.source, target=e.target, type=e.type,
                          attributes=e.attributes, weight=e.weight, evidence=e.evidence)
             for e in store.all_edges()]
    return GraphOut(nodes=nodes, edges=edges)


@router.get("/neighborhood/{entity_id}", response_model=GraphOut)
def get_neighborhood(entity_id: str, hops: int = 1,
                      user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                      store: GraphStore = Depends(get_store)):
    if not store.get_node(entity_id):
        raise HTTPException(404, "Entity not found.")
    nodes, edges = store.neighbors(entity_id, hops=hops)
    return GraphOut(
        nodes=[EntityOut(id=n.id, type=n.type, label=n.label, attributes=n.attributes,
                          source_count=len(n.source_documents)) for n in nodes],
        edges=[RelationOut(id=e.id, source=e.source, target=e.target, type=e.type,
                            attributes=e.attributes, weight=e.weight, evidence=e.evidence) for e in edges],
    )


@router.get("/path", response_model=PathResult)
def get_path(source: str, target: str, max_hops: int = 6,
             user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
             store: GraphStore = Depends(get_store)):
    return find_path(store, source, target, max_hops=max_hops)
