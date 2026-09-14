from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_store_for, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore
from app.db.models import EntityResolutionDecision
from app.models.schemas import EntityOut, ResolutionCandidateOut, ResolutionDecisionIn, ResolutionDecisionOut
from app.resolution.entity_resolution import MergeCandidate, apply_merge, resolve_candidates
from app.services import audit

router = APIRouter(prefix="/entities", tags=["entities"])

_AUTO_MERGE_THRESHOLD = 97.0


def _pair_key(a: str, b: str) -> tuple[str, str]:
    """Order-independent key so a decision recorded as (X, Y) also matches
    a later candidate surfaced as (Y, X) -- resolve_candidates() picks
    keep/merge by source-document count, which can flip which side is
    "keep" if new evidence arrives between two runs."""
    return (a, b) if a <= b else (b, a)


@router.get("/search", response_model=list[EntityOut])
def search_entities(q: str = Query(..., min_length=1), type: str | None = None, limit: int = 25,
                     user: AuthUser = Depends(require_role("investigator", "analyst", "admin", "viewer")),
                     store: GraphStore = Depends(get_store_for)):
    nodes = store.search_nodes(q, type=type, limit=limit)
    return [EntityOut(id=n.id, type=n.type, label=n.label, attributes=n.attributes,
                       source_count=len(n.source_documents)) for n in nodes]


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: str, user: AuthUser = Depends(require_role("investigator", "analyst", "admin", "viewer")),
                store: GraphStore = Depends(get_store_for)):
    node = store.get_node(entity_id)
    if not node:
        raise HTTPException(404, "Entity not found.")
    return EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                      source_count=len(node.source_documents))


@router.get("/resolution/candidates", response_model=list[ResolutionCandidateOut])
def get_merge_candidates(entity_type: str = "PERSON", investigation_id: str | None = None,
                          user: AuthUser = Depends(require_role("analyst", "admin")),
                          store: GraphStore = Depends(get_store_for), db: Session = Depends(get_db)):
    # Wire entity_resolution_decisions into the actual workflow: a pair an
    # analyst already REJECTED must not keep resurfacing every time this
    # endpoint is called (see app/db/models.py:EntityResolutionDecision's
    # docstring) -- an already-APPROVED pair also drops out naturally since
    # apply_merge() removes the merged node from the graph, so
    # resolve_candidates() simply never sees it again.
    rejected: set[tuple[str, str]] = set()
    if investigation_id:
        rows = (db.query(EntityResolutionDecision)
                .filter(EntityResolutionDecision.investigation_id == investigation_id,
                        EntityResolutionDecision.decision == "REJECTED").all())
        rejected = {_pair_key(r.keep_id, r.merge_id) for r in rows}

    candidates = resolve_candidates(store, entity_type)
    out: list[ResolutionCandidateOut] = []
    for c in candidates:
        if _pair_key(c.keep_id, c.merge_id) in rejected:
            continue
        keep_node = store.get_node(c.keep_id)
        merge_node = store.get_node(c.merge_id)
        reasons = [f"Name similarity {c.name_similarity:.0f}%"]
        if c.shared_neighbors:
            reasons.append(f"{len(c.shared_neighbors)} shared connection(s) in common")
        else:
            reasons.append("Near-exact name match (no shared connection required)")
        out.append(ResolutionCandidateOut(
            keep_id=c.keep_id, merge_id=c.merge_id, keep_label=c.keep_label, merge_label=c.merge_label,
            confidence=c.name_similarity, matching_reasons=reasons,
            source_references={
                "keep": sorted(keep_node.source_documents) if keep_node else [],
                "merge": sorted(merge_node.source_documents) if merge_node else [],
            },
            decision_status="AUTO_MERGE_ELIGIBLE" if c.name_similarity >= _AUTO_MERGE_THRESHOLD else "REVIEW_REQUIRED",
        ))
    return out


@router.post("/resolution/decide", response_model=ResolutionDecisionOut)
def decide_resolution(body: ResolutionDecisionIn, investigation_id: str,
                       user: AuthUser = Depends(require_role("analyst", "admin")),
                       store: GraphStore = Depends(get_store_for), db: Session = Depends(get_db)):
    """
    Record an analyst's accept/reject decision on a merge candidate --
    the workflow entity_resolution_decisions existed for as a table but
    wasn't wired into (see docs/KNOT6_ARCHITECTURE.md's "honest current
    limitations"). APPROVED performs the actual merge (same
    `apply_merge()` the older query-param `/resolution/merge` route uses);
    REJECTED only records the decision so `get_merge_candidates` above
    stops resurfacing this exact pair.
    """
    if body.decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(400, "decision must be APPROVED or REJECTED.")

    if body.decision == "APPROVED":
        apply_merge(store, MergeCandidate(keep_id=body.keep_id, merge_id=body.merge_id, keep_label="",
                                           merge_label="", name_similarity=100.0, shared_neighbors=[],
                                           reason="analyst-approved"))
        audit.log(actor=user.username, action="MERGE_ENTITIES", target=body.keep_id,
                  details={"merged": body.merge_id, "reason": body.reason}, investigation_id=investigation_id)

    row = EntityResolutionDecision(
        investigation_id=investigation_id, keep_id=body.keep_id, merge_id=body.merge_id,
        decision=body.decision, reason=body.reason, decided_by=user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit.log(actor=user.username, action=f"ENTITY_RESOLUTION_{body.decision}", target=body.keep_id,
              details={"merge_id": body.merge_id, "reason": body.reason}, investigation_id=investigation_id)
    return ResolutionDecisionOut.model_validate(row)


@router.get("/resolution/decisions", response_model=list[ResolutionDecisionOut])
def list_resolution_decisions(investigation_id: str,
                               user: AuthUser = Depends(require_role("analyst", "admin")),
                               db: Session = Depends(get_db)):
    rows = (db.query(EntityResolutionDecision)
            .filter(EntityResolutionDecision.investigation_id == investigation_id)
            .order_by(EntityResolutionDecision.decided_at.desc()).all())
    return [ResolutionDecisionOut.model_validate(r) for r in rows]


@router.post("/resolution/merge")
def merge_entities(keep_id: str, merge_id: str, investigation_id: str | None = None,
                    user: AuthUser = Depends(require_role("analyst", "admin")),
                    store: GraphStore = Depends(get_store_for)):
    apply_merge(store, MergeCandidate(keep_id=keep_id, merge_id=merge_id, keep_label="", merge_label="",
                                       name_similarity=100.0, shared_neighbors=[], reason="manual"))
    # investigation_id (KNOT6 Case Intelligence): explicit now so a merge
    # surfaces as an "entity resolved" Recent Development for the right
    # investigation -- previously unset, so scoped merges never showed up
    # there even though the merge itself was already investigation-scoped
    # via `store`.
    audit.log(actor=user.username, action="MERGE_ENTITIES", target=keep_id,
              details={"merged": merge_id}, investigation_id=investigation_id)
    return {"status": "merged", "keep_id": keep_id, "merge_id": merge_id}
