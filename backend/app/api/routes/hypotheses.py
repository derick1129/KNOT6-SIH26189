"""
Hypothesis Lab persistence API.

Ethics-language guarantee (non-negotiable, per KNOT6_PROJECT_SPECIFICATION.pdf):
this router never lets a hypothesis be described as "true", "confirmed", or
a guilt determination -- `status` is restricted to the five investigative
states in HYPOTHESIS_STATUSES, and every narrated assessment
(app/services/hypothesis.py:narrate_assessment) is phrased as what the
current tagged evidence supports/contradicts, explicitly requiring
investigator verification.

RBAC (matching this codebase's existing role-gate conventions, e.g.
app/api/routes/evidence.py): viewer reads only; investigator/analyst can
create, update status, and tag evidence/notes; admin has full access
including delete. Every mutation is audited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_store_for, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore, ScopedGraphStore, get_graph_store
from app.db.models import Evidence, Hypothesis, HypothesisEvidence, new_id, utcnow
from app.models.schemas import (
    HYPOTHESIS_STATUSES, HypothesisCreate, HypothesisDetailOut, HypothesisEvidenceIn, HypothesisEvidenceOut,
    HypothesisNoteIn, HypothesisNoteOut, HypothesisOut, HypothesisUpdate,
)
from app.services import audit
from app.services.hypothesis import to_detail, to_summary

router = APIRouter(tags=["hypotheses"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")
_WRITE_ROLES = ("investigator", "analyst", "admin")
_DELETE_ROLES = ("admin",)


def _get_hypothesis(hypothesis_id: str, db: Session) -> Hypothesis:
    h = db.get(Hypothesis, hypothesis_id)
    if not h:
        raise HTTPException(404, "Hypothesis not found.")
    return h


def _store_for(investigation_id: str) -> GraphStore:
    return ScopedGraphStore(get_graph_store(), investigation_id)


@router.get("/investigations/{investigation_id}/hypotheses", response_model=list[HypothesisOut])
def list_hypotheses(investigation_id: str, status: str | None = None, case_id: str | None = None,
                     user: AuthUser = Depends(require_role(*_READ_ROLES)),
                     db: Session = Depends(get_db)):
    query = db.query(Hypothesis).filter(Hypothesis.investigation_id == investigation_id)
    if status:
        query = query.filter(Hypothesis.status == status)
    if case_id:
        query = query.filter(Hypothesis.case_id == case_id)
    rows = query.order_by(Hypothesis.updated_at.desc()).all()
    return [to_summary(db, h) for h in rows]


@router.post("/investigations/{investigation_id}/hypotheses", response_model=HypothesisDetailOut)
def create_hypothesis(investigation_id: str, body: HypothesisCreate,
                       user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                       db: Session = Depends(get_db)):
    h = Hypothesis(
        investigation_id=investigation_id, case_id=body.case_id, title=body.title,
        description=body.description, subject_entity_id=body.subject_entity_id,
        target_entity_id=body.target_entity_id, related_entity_ids=body.related_entity_ids,
        created_by=user.username,
    )
    db.add(h)
    db.commit()
    db.refresh(h)

    audit.log(actor=user.username, action="CREATE_HYPOTHESIS", target=h.id,
              details={"title": h.title}, investigation_id=investigation_id)
    return to_detail(_store_for(investigation_id), db, h)


@router.get("/hypotheses/{hypothesis_id}", response_model=HypothesisDetailOut)
def get_hypothesis(hypothesis_id: str, user: AuthUser = Depends(require_role(*_READ_ROLES)),
                    db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    return to_detail(_store_for(h.investigation_id), db, h)


@router.patch("/hypotheses/{hypothesis_id}", response_model=HypothesisDetailOut)
def update_hypothesis(hypothesis_id: str, body: HypothesisUpdate,
                       user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                       db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    changes: dict[str, object] = {}

    if body.status is not None:
        if body.status not in HYPOTHESIS_STATUSES:
            raise HTTPException(400, f"status must be one of {HYPOTHESIS_STATUSES}.")
        if body.status != h.status:
            changes["status"] = {"from": h.status, "to": body.status}
        h.status = body.status
    if body.title is not None:
        h.title = body.title
    if body.description is not None:
        h.description = body.description
    if body.subject_entity_id is not None:
        h.subject_entity_id = body.subject_entity_id or None
    if body.target_entity_id is not None:
        h.target_entity_id = body.target_entity_id or None
    if body.related_entity_ids is not None:
        h.related_entity_ids = body.related_entity_ids

    db.commit()
    db.refresh(h)

    audit.log(actor=user.username, action="UPDATE_HYPOTHESIS", target=h.id,
              details=changes or {"note": "fields updated"}, investigation_id=h.investigation_id)
    return to_detail(_store_for(h.investigation_id), db, h)


@router.delete("/hypotheses/{hypothesis_id}")
def delete_hypothesis(hypothesis_id: str, user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
                       db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    investigation_id, title = h.investigation_id, h.title
    db.delete(h)
    db.commit()

    audit.log(actor=user.username, action="DELETE_HYPOTHESIS", target=hypothesis_id,
              details={"title": title}, investigation_id=investigation_id)
    return {"status": "deleted", "id": hypothesis_id}


@router.post("/hypotheses/{hypothesis_id}/evidence", response_model=HypothesisEvidenceOut)
def add_hypothesis_evidence(hypothesis_id: str, body: HypothesisEvidenceIn,
                             user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                             db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    if body.relationship_type not in ("SUPPORTING", "CONTRADICTING"):
        raise HTTPException(400, "relationship_type must be SUPPORTING or CONTRADICTING.")

    ev = db.get(Evidence, body.evidence_id)
    if not ev or ev.investigation_id != h.investigation_id:
        raise HTTPException(404, "Evidence not found in this hypothesis's investigation.")

    link = HypothesisEvidence(
        hypothesis_id=hypothesis_id, evidence_id=body.evidence_id,
        relationship_type=body.relationship_type, note=body.note, created_by=user.username,
    )
    db.add(link)
    h.updated_at = utcnow()
    db.commit()
    db.refresh(link)

    audit.log(actor=user.username, action="TAG_HYPOTHESIS_EVIDENCE", target=hypothesis_id,
              details={"evidence_id": body.evidence_id, "relationship_type": body.relationship_type},
              investigation_id=h.investigation_id)
    return HypothesisEvidenceOut(
        id=link.id, hypothesis_id=link.hypothesis_id, evidence_id=link.evidence_id,
        relationship_type=link.relationship_type, note=link.note, created_by=link.created_by,
        created_at=link.created_at, evidence=None,
    )


@router.delete("/hypotheses/{hypothesis_id}/evidence/{link_id}")
def remove_hypothesis_evidence(hypothesis_id: str, link_id: str,
                                user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                                db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    link = db.get(HypothesisEvidence, link_id)
    if not link or link.hypothesis_id != hypothesis_id:
        raise HTTPException(404, "Evidence tag not found on this hypothesis.")
    db.delete(link)
    h.updated_at = utcnow()
    db.commit()

    audit.log(actor=user.username, action="UNTAG_HYPOTHESIS_EVIDENCE", target=hypothesis_id,
              details={"evidence_id": link.evidence_id}, investigation_id=h.investigation_id)
    return {"status": "removed", "id": link_id}


@router.post("/hypotheses/{hypothesis_id}/notes", response_model=HypothesisNoteOut)
def add_hypothesis_note(hypothesis_id: str, body: HypothesisNoteIn,
                         user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                         db: Session = Depends(get_db)):
    h = _get_hypothesis(hypothesis_id, db)
    note = {"id": new_id(), "author": user.username, "text": body.text,
             "created_at": utcnow().isoformat()}
    h.notes = [*(h.notes or []), note]
    h.updated_at = utcnow()
    db.commit()

    audit.log(actor=user.username, action="ADD_HYPOTHESIS_NOTE", target=hypothesis_id,
              details={}, investigation_id=h.investigation_id)
    return HypothesisNoteOut(**note)
