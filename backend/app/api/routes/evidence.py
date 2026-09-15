"""
KNOT6 Phase 1: Evidence metadata + registration, nested under a case.

Persistent metadata + a storage reference, and running the file through the
**existing, unmodified** ingestion pipeline (`app/services/pipeline.py`)
scoped to the owning investigation via `ScopedGraphStore`. The actual
pipeline-running logic (`process_evidence`, extraction helpers, and the
protected-demo-investigation guard) lives in
`app/services/evidence_processing.py` so it can be replayed from
`app/services/graph_recovery.py` too -- see that module's docstring.

Phase 4 addition: SHA-256 hashing at upload time (`Evidence.sha256_hash`) --
see app/services/integrity.py for the hash computation and the
verify-integrity flow exposed by app/api/routes/integrity.py.

Multi-format addition: PDF/DOCX/XLSX/JSON now extract real text/records
before reaching the same, still-unmodified `ingest_text_document`/
`ingest_structured` functions (see app/ingestion/document_extraction.py) --
TXT and CSV support is untouched. A file whose content can't actually be
extracted (a scanned PDF, a corrupt DOCX/XLSX, malformed JSON) is reported
as FAILED with the real reason, never silently treated as successfully
processed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import AuthUser
from app.db.models import Case, Evidence, Investigation
from app.models.schemas import EvidenceOut
from app.services import audit
from app.services.evidence_processing import ensure_not_demo_protected, process_evidence
from app.services.integrity import sha256_bytes
from app.services.storage import get_storage

router = APIRouter(prefix="/investigations/{investigation_id}/cases/{case_id}/evidence", tags=["evidence"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")
_WRITE_ROLES = ("investigator", "analyst", "admin")  # matches the existing ingestion role gate

# Evidence.source_type (PS-shaped, per KNOT6 Phase 1 spec) -> the existing
# pipeline's source_type vocabulary (app/api/routes/ingestion.py). Kept as an
# explicit table rather than a case-fold so the mapping is visible and
# reviewable, not implicit.
_SOURCE_TYPES = (
    "FIR", "POLICE_REPORT", "CDR", "FINANCIAL_TRANSACTION", "SURVEILLANCE",
    "SOCIAL_MEDIA", "CRIMINAL_HISTORY", "INTELLIGENCE_REPORT", "OTHER",
)


def _require_case(investigation_id: str, case_id: str, db: Session) -> tuple[Investigation, Case]:
    investigation = db.get(Investigation, investigation_id)
    if not investigation:
        raise HTTPException(404, "Investigation not found.")
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    return investigation, case


@router.post("", response_model=EvidenceOut)
async def upload_evidence(investigation_id: str, case_id: str,
                           source_type: str = Form(...), description: str = Form(""),
                           file: UploadFile = File(...),
                           user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                           db: Session = Depends(get_db)):
    investigation, _case = _require_case(investigation_id, case_id, db)
    ensure_not_demo_protected(investigation)
    if source_type not in _SOURCE_TYPES:
        raise HTTPException(400, f"source_type must be one of {_SOURCE_TYPES}.")

    data = await file.read()
    storage_ref = get_storage().save(investigation_id, file.filename or "upload", data)
    # Evidence Integrity (Phase 4): hash the exact bytes just written to
    # storage, once, at registration time -- this is the reference every
    # later verify-integrity check re-derives and compares against.
    file_hash = sha256_bytes(data)

    evidence = Evidence(
        investigation_id=investigation_id, case_id=case_id,
        filename=storage_ref, original_filename=file.filename or "upload",
        source_type=source_type, mime_type=file.content_type or "", file_size=len(data),
        storage_path=storage_ref, uploaded_by=user.username, description=description,
        processing_status="UPLOADED", sha256_hash=file_hash,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)

    process_evidence(evidence, data, db)

    audit.log(actor=user.username, action="UPLOAD_EVIDENCE", target=evidence.id,
              details={"source_type": source_type, "filename": evidence.original_filename,
                        "processing_status": evidence.processing_status, "sha256_hash": file_hash},
              investigation_id=investigation_id)
    return EvidenceOut.model_validate(evidence)


@router.get("", response_model=list[EvidenceOut])
def list_evidence(investigation_id: str, case_id: str,
                   user: AuthUser = Depends(require_role(*_READ_ROLES)),
                   db: Session = Depends(get_db)):
    _require_case(investigation_id, case_id, db)
    rows = (db.query(Evidence).filter(Evidence.case_id == case_id)
            .order_by(Evidence.uploaded_at.desc()).all())
    return [EvidenceOut.model_validate(r) for r in rows]


@router.get("/{evidence_id}", response_model=EvidenceOut)
def get_evidence(investigation_id: str, case_id: str, evidence_id: str,
                  user: AuthUser = Depends(require_role(*_READ_ROLES)),
                  db: Session = Depends(get_db)):
    _require_case(investigation_id, case_id, db)
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.case_id != case_id:
        raise HTTPException(404, "Evidence not found in this case.")
    return EvidenceOut.model_validate(ev)


@router.get("/{evidence_id}/status")
def get_evidence_status(investigation_id: str, case_id: str, evidence_id: str,
                         user: AuthUser = Depends(require_role(*_READ_ROLES)),
                         db: Session = Depends(get_db)):
    _require_case(investigation_id, case_id, db)
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.case_id != case_id:
        raise HTTPException(404, "Evidence not found in this case.")
    return {"id": ev.id, "processing_status": ev.processing_status, "processing_summary": ev.processing_summary}
