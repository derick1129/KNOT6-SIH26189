"""
KNOT6 Phase 4: Evidence Integrity + tamper-evident audit chain -- the API
surface over app/services/integrity.py.

Flat `/api/evidence/{evidence_id}/...` routes (not nested under
investigation/case, unlike app/api/routes/evidence.py's upload/list routes)
because `Evidence.id` is already a globally unique UUID and the PS spec
calls these out as top-level endpoints; every route still enforces the same
RBAC roles the rest of evidence handling uses.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import AuthUser
from app.db.models import Evidence
from app.models.schemas import AuditChainVerifyOut, EvidenceIntegrityOut, EvidenceIntegrityVerifyOut
from app.services import audit
from app.services.integrity import verify_audit_chain, verify_evidence

router = APIRouter(tags=["integrity"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")


def _get_evidence(evidence_id: str, db: Session) -> Evidence:
    ev = db.get(Evidence, evidence_id)
    if not ev:
        raise HTTPException(404, "Evidence not found.")
    return ev


@router.get("/evidence/{evidence_id}/integrity", response_model=EvidenceIntegrityOut)
def get_evidence_integrity(evidence_id: str, user: AuthUser = Depends(require_role(*_READ_ROLES)),
                            db: Session = Depends(get_db)):
    ev = _get_evidence(evidence_id, db)
    return EvidenceIntegrityOut(
        evidence_id=ev.id, sha256_hash=ev.sha256_hash, uploaded_by=ev.uploaded_by,
        uploaded_at=ev.uploaded_at, source_type=ev.source_type, original_filename=ev.original_filename,
        has_reference_hash=bool(ev.sha256_hash),
    )


@router.post("/evidence/{evidence_id}/verify-integrity", response_model=EvidenceIntegrityVerifyOut)
def verify_evidence_integrity(evidence_id: str, user: AuthUser = Depends(require_role(*_READ_ROLES)),
                               db: Session = Depends(get_db)):
    ev = _get_evidence(evidence_id, db)
    result = verify_evidence(ev)
    # Every integrity check is itself an accountable action (the PS spec
    # calls out "evidence access" as an audit-worthy event) -- logged
    # regardless of outcome, so a pattern of repeated failed verifications
    # against one item is itself visible in the audit trail.
    audit.log(actor=user.username, action="VERIFY_EVIDENCE_INTEGRITY", target=ev.id,
              details={"status": result.status, "stored_hash": result.stored_hash,
                        "computed_hash": result.computed_hash},
              investigation_id=ev.investigation_id)
    return EvidenceIntegrityVerifyOut(
        evidence_id=result.evidence_id, status=result.status, stored_hash=result.stored_hash,
        computed_hash=result.computed_hash, checked_at=result.checked_at, message=result.message,
    )


@router.get("/audit/verify", response_model=AuditChainVerifyOut)
def verify_audit_integrity(user: AuthUser = Depends(require_role("admin")),
                            db: Session = Depends(get_db)):
    result = verify_audit_chain(db)
    return AuditChainVerifyOut(
        status=result.status, entries_checked=result.entries_checked,
        first_broken_entry_id=result.first_broken_entry_id, first_broken_seq=result.first_broken_seq,
        message=result.message, checked_at=result.checked_at,
    )
