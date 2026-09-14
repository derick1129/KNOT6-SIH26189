"""KNOT6 Phase 1: Cases, nested under an investigation. See investigations.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import AuthUser
from app.db.models import Case, Evidence, Investigation
from app.models.schemas import CaseCreate, CaseOut, CaseUpdate
from app.services import audit

router = APIRouter(prefix="/investigations/{investigation_id}/cases", tags=["cases"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")
_WRITE_ROLES = ("investigator", "admin")

_VALID_STATUSES = ("OPEN", "UNDER_REVIEW", "CLOSED", "ARCHIVED")
_VALID_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _require_investigation(investigation_id: str, db: Session) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    return inv


def _to_out(case: Case, db: Session) -> CaseOut:
    evidence_count = db.query(Evidence).filter(Evidence.case_id == case.id).count()
    return CaseOut(
        id=case.id, investigation_id=case.investigation_id, case_number=case.case_number,
        title=case.title, description=case.description, status=case.status, priority=case.priority,
        created_by=case.created_by, created_at=case.created_at, updated_at=case.updated_at,
        evidence_count=evidence_count,
    )


@router.post("", response_model=CaseOut)
def create_case(investigation_id: str, payload: CaseCreate,
                 user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                 db: Session = Depends(get_db)):
    _require_investigation(investigation_id, db)
    if payload.priority not in _VALID_PRIORITIES:
        raise HTTPException(400, f"priority must be one of {_VALID_PRIORITIES}.")
    if db.query(Case).filter(Case.case_number == payload.case_number).first():
        raise HTTPException(409, f"Case number '{payload.case_number}' is already in use.")
    case = Case(investigation_id=investigation_id, case_number=payload.case_number,
                title=payload.title, description=payload.description, priority=payload.priority,
                created_by=user.username)
    db.add(case)
    db.commit()
    db.refresh(case)
    audit.log(actor=user.username, action="CREATE_CASE", target=case.id,
              details={"case_number": case.case_number}, investigation_id=investigation_id)
    return _to_out(case, db)


@router.get("", response_model=list[CaseOut])
def list_cases(investigation_id: str,
               user: AuthUser = Depends(require_role(*_READ_ROLES)),
               db: Session = Depends(get_db)):
    _require_investigation(investigation_id, db)
    cases = (db.query(Case).filter(Case.investigation_id == investigation_id)
             .order_by(Case.created_at.desc()).all())
    return [_to_out(c, db) for c in cases]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(investigation_id: str, case_id: str,
             user: AuthUser = Depends(require_role(*_READ_ROLES)),
             db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    return _to_out(case, db)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(investigation_id: str, case_id: str, payload: CaseUpdate,
                 user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                 db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    if payload.title is not None:
        case.title = payload.title
    if payload.description is not None:
        case.description = payload.description
    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise HTTPException(400, f"status must be one of {_VALID_STATUSES}.")
        case.status = payload.status
    if payload.priority is not None:
        if payload.priority not in _VALID_PRIORITIES:
            raise HTTPException(400, f"priority must be one of {_VALID_PRIORITIES}.")
        case.priority = payload.priority
    db.commit()
    db.refresh(case)
    audit.log(actor=user.username, action="UPDATE_CASE", target=case.id,
              details=payload.model_dump(exclude_none=True), investigation_id=investigation_id)
    return _to_out(case, db)


@router.post("/{case_id}/close", response_model=CaseOut)
def close_case(investigation_id: str, case_id: str,
                user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    case.status = "CLOSED"
    db.commit()
    db.refresh(case)
    audit.log(actor=user.username, action="CLOSE_CASE", target=case.id, investigation_id=investigation_id)
    return _to_out(case, db)


@router.post("/{case_id}/archive", response_model=CaseOut)
def archive_case(investigation_id: str, case_id: str,
                  user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                  db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    case.status = "ARCHIVED"
    db.commit()
    db.refresh(case)
    audit.log(actor=user.username, action="ARCHIVE_CASE", target=case.id, investigation_id=investigation_id)
    return _to_out(case, db)
