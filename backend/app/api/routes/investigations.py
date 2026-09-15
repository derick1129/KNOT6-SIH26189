"""
KNOT6 Phase 1: Investigations.

Investigation -> Case -> Evidence is the top of the persistence hierarchy
described in docs/KNOT6_ARCHITECTURE.md. All storage here is PostgreSQL
(`app/db/models.py:Investigation`) -- the graph itself is untouched by
these routes; see `graph.py` for graph endpoints, now investigation-scoped
via the optional `investigation_id` parameter on `get_store_for`
(`app/api/deps.py`).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import AuthUser
from app.db.graph_store import ScopedGraphStore, get_graph_store
from app.db.models import Case, Evidence, Investigation
from app.models.schemas import (
    EvidenceOut, FinancialIntelligenceOut, InvestigationCreate, InvestigationOut, InvestigationTimelineOut,
    InvestigationUpdate, UndatedRelation,
)
from app.services import audit
from app.services.financial import build_financial_intelligence
from app.services.timeline import build_investigation_timeline

router = APIRouter(prefix="/investigations", tags=["investigations"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")
_WRITE_ROLES = ("investigator", "admin")


def _to_out(inv: Investigation, db: Session) -> InvestigationOut:
    case_count = db.query(Case).filter(Case.investigation_id == inv.id).count()
    return InvestigationOut(
        id=inv.id, name=inv.name, description=inv.description, status=inv.status,
        is_demo_seed=inv.is_demo_seed, created_by=inv.created_by,
        created_at=inv.created_at, updated_at=inv.updated_at, case_count=case_count,
    )


@router.post("", response_model=InvestigationOut)
def create_investigation(payload: InvestigationCreate,
                          user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                          db: Session = Depends(get_db)):
    inv = Investigation(name=payload.name, description=payload.description, created_by=user.username)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    audit.log(actor=user.username, action="CREATE_INVESTIGATION", target=inv.id,
              details={"name": inv.name}, investigation_id=inv.id)
    return _to_out(inv, db)


@router.get("", response_model=list[InvestigationOut])
def list_investigations(status_filter: str | None = None,
                         user: AuthUser = Depends(require_role(*_READ_ROLES)),
                         db: Session = Depends(get_db)):
    query = db.query(Investigation)
    if status_filter:
        query = query.filter(Investigation.status == status_filter)
    investigations = query.order_by(Investigation.created_at.desc()).all()
    return [_to_out(inv, db) for inv in investigations]


@router.get("/{investigation_id}", response_model=InvestigationOut)
def get_investigation(investigation_id: str,
                       user: AuthUser = Depends(require_role(*_READ_ROLES)),
                       db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    return _to_out(inv, db)


@router.patch("/{investigation_id}", response_model=InvestigationOut)
def update_investigation(investigation_id: str, payload: InvestigationUpdate,
                          user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                          db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    if payload.name is not None:
        inv.name = payload.name
    if payload.description is not None:
        inv.description = payload.description
    if payload.status is not None:
        if payload.status not in ("ACTIVE", "ARCHIVED", "CLOSED"):
            raise HTTPException(400, "status must be one of ACTIVE, ARCHIVED, CLOSED.")
        inv.status = payload.status
    db.commit()
    db.refresh(inv)
    audit.log(actor=user.username, action="UPDATE_INVESTIGATION", target=inv.id,
              details=payload.model_dump(exclude_none=True), investigation_id=inv.id)
    return _to_out(inv, db)


@router.get("/{investigation_id}/evidence", response_model=list[EvidenceOut])
def list_investigation_evidence(investigation_id: str,
                                 user: AuthUser = Depends(require_role(*_READ_ROLES)),
                                 db: Session = Depends(get_db)):
    """
    KNOT6 frontend milestone: Evidence Vault needs an investigation-wide
    view, not just per-case (the only listing Phase 1 shipped). Purely
    additive -- reads the same `evidence` table Phase 1 already writes,
    no schema change, no existing endpoint touched.
    """
    if not db.get(Investigation, investigation_id):
        raise HTTPException(404, "Investigation not found.")
    rows = (db.query(Evidence).filter(Evidence.investigation_id == investigation_id)
            .order_by(Evidence.uploaded_at.desc()).all())
    return [EvidenceOut.model_validate(r) for r in rows]


@router.get("/{investigation_id}/timeline", response_model=InvestigationTimelineOut)
def get_investigation_timeline(
    investigation_id: str,
    event_type: list[str] | None = Query(default=None, description="Filter to one or more kinds, e.g. CALL,TRANSACTION"),
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ascending: bool = True,
    user: AuthUser = Depends(require_role(*_READ_ROLES)),
    db: Session = Depends(get_db),
):
    """
    Full chronological reconstruction for this investigation -- evidence
    registration, calls, transactions, dated document relationships, and
    case/investigation lifecycle events, all real and already in the
    system (see app/services/timeline.py). Never fabricates a timestamp:
    relationships with no reliable date are returned separately under
    `undated_relations` instead of being dropped or backdated.
    """
    if not db.get(Investigation, investigation_id):
        raise HTTPException(404, "Investigation not found.")
    store = ScopedGraphStore(get_graph_store(), investigation_id)
    types = set(event_type) if event_type else None
    events, undated = build_investigation_timeline(
        store, db, investigation_id, event_types=types, entity_id=entity_id,
        date_from=date_from, date_to=date_to, ascending=ascending,
    )
    return InvestigationTimelineOut(
        investigation_id=investigation_id, events=events,
        undated_relations=[UndatedRelation(**u) for u in undated], total_events=len(events),
    )


@router.get("/{investigation_id}/financial", response_model=FinancialIntelligenceOut)
def get_investigation_financial(investigation_id: str,
                                 user: AuthUser = Depends(require_role(*_READ_ROLES)),
                                 db: Session = Depends(get_db)):
    """Financial Intelligence: accounts, transaction totals, counterparties,
    circular flows and suspicious patterns -- computed server-side from real
    graph/transaction data (see app/services/financial.py) rather than
    recomputed client-side in multiple places."""
    if not db.get(Investigation, investigation_id):
        raise HTTPException(404, "Investigation not found.")
    store = ScopedGraphStore(get_graph_store(), investigation_id)
    return build_financial_intelligence(store, investigation_id)


@router.post("/{investigation_id}/archive", response_model=InvestigationOut)
def archive_investigation(investigation_id: str,
                           user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                           db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    inv.status = "ARCHIVED"
    db.commit()
    db.refresh(inv)
    audit.log(actor=user.username, action="ARCHIVE_INVESTIGATION", target=inv.id,
              investigation_id=inv.id)
    return _to_out(inv, db)


@router.post("/{investigation_id}/reseed-demo")
def reseed_demo_investigation_route(investigation_id: str,
                                     user: AuthUser = Depends(require_role("admin")),
                                     db: Session = Depends(get_db)):
    """
    Restore the bundled demo investigation to its canonical, seed_demo.py-
    generated graph -- see app/services/graph_recovery.py. Admin-only, and
    refuses outright on anything not flagged `is_demo_seed` (a real
    investigation has no canonical source to restore from). This is the
    proper fix for the demo dataset having been polluted by a real upload
    before `ensure_not_demo_protected` existed: restore from source, don't
    hand-edit the graph.
    """
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    if not inv.is_demo_seed:
        raise HTTPException(400, f"'{inv.name}' is not the protected demo investigation; nothing to reseed.")

    from app.services.graph_recovery import reseed_demo_investigation
    result = reseed_demo_investigation(inv, db)
    audit.log(actor=user.username, action="RESEED_DEMO_INVESTIGATION", target=inv.id,
              details={k: v for k, v in result.items() if k != "seed_summary"},
              investigation_id=inv.id)
    return result
