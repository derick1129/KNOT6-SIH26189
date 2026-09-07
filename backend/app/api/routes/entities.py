from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_store, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore
from app.models.schemas import EntityOut
from app.resolution.entity_resolution import apply_merge, resolve_candidates
from app.services import audit

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/search", response_model=list[EntityOut])
def search_entities(q: str = Query(..., min_length=1), type: str | None = None, limit: int = 25,
                     user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                     store: GraphStore = Depends(get_store)):
    nodes = store.search_nodes(q, type=type, limit=limit)
    return [EntityOut(id=n.id, type=n.type, label=n.label, attributes=n.attributes,
                       source_count=len(n.source_documents)) for n in nodes]


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: str, user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                store: GraphStore = Depends(get_store)):
    node = store.get_node(entity_id)
    if not node:
        raise HTTPException(404, "Entity not found.")
    return EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                      source_count=len(node.source_documents))


@router.get("/resolution/candidates")
def get_merge_candidates(entity_type: str = "PERSON",
                          user: AuthUser = Depends(require_role("analyst", "admin")),
                          store: GraphStore = Depends(get_store)):
    candidates = resolve_candidates(store, entity_type)
    return [
        {"keep_id": c.keep_id, "merge_id": c.merge_id, "keep_label": c.keep_label,
         "merge_label": c.merge_label, "name_similarity": c.name_similarity,
         "shared_neighbors": c.shared_neighbors, "reason": c.reason}
        for c in candidates
    ]


@router.post("/resolution/merge")
def merge_entities(keep_id: str, merge_id: str,
                    user: AuthUser = Depends(require_role("analyst", "admin")),
                    store: GraphStore = Depends(get_store)):
    from app.resolution.entity_resolution import MergeCandidate
    apply_merge(store, MergeCandidate(keep_id=keep_id, merge_id=merge_id, keep_label="", merge_label="",
                                       name_similarity=100.0, shared_neighbors=[], reason="manual"))
    audit.log(actor=user.username, action="MERGE_ENTITIES", target=keep_id, details={"merged": merge_id})
    return {"status": "merged", "keep_id": keep_id, "merge_id": merge_id}
