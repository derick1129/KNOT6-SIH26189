"""
KNOT6 Phase 1: Evidence metadata + registration, nested under a case.

Persistent metadata + a storage reference, and running the file through the
**existing, unmodified** ingestion pipeline (`app/services/pipeline.py`)
scoped to the owning investigation via `ScopedGraphStore`.

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

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import AuthUser
from app.db.graph_store import ScopedGraphStore, get_graph_store
from app.db.models import Case, Evidence, Investigation
from app.ingestion.document_extraction import extract_json, extract_records_from_xlsx, extract_text_from_docx, extract_text_from_pdf
from app.models.schemas import EvidenceOut
from app.services import audit
from app.services.integrity import sha256_bytes
from app.services.pipeline import ingest_structured, ingest_text_document
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
_TEXT_PIPELINE_SOURCE = {
    "FIR": "fir", "POLICE_REPORT": "fir", "SURVEILLANCE": "surveillance",
    "SOCIAL_MEDIA": "social_media", "INTELLIGENCE_REPORT": "intel_report",
}
_STRUCTURED_PIPELINE_SOURCE = {
    "CDR": "cdr", "FINANCIAL_TRANSACTION": "financial", "CRIMINAL_HISTORY": "criminal_history",
}


def _require_case(investigation_id: str, case_id: str, db: Session) -> Case:
    if not db.get(Investigation, investigation_id):
        raise HTTPException(404, "Investigation not found.")
    case = db.get(Case, case_id)
    if not case or case.investigation_id != investigation_id:
        raise HTTPException(404, "Case not found in this investigation.")
    return case


_SUPPORTED_TEXT_EXTENSIONS = (".txt", ".pdf", ".docx", ".json")
_SUPPORTED_STRUCTURED_EXTENSIONS = (".csv", ".xlsx", ".json")


def _extract_text(ext: str, data: bytes) -> tuple[str | None, str | None]:
    """Returns (text, failure_reason) -- exactly one is non-None."""
    if ext == ".txt":
        return data.decode("utf-8-sig", errors="replace"), None
    if ext == ".pdf":
        result = extract_text_from_pdf(data)
        return (result.text, None) if result.ok else (None, result.warning)
    if ext == ".docx":
        result = extract_text_from_docx(data)
        return (result.text, None) if result.ok else (None, result.warning)
    if ext == ".json":
        text_result, _ = extract_json(data)
        if text_result is None:
            return None, "JSON content is record-shaped, not text-shaped -- check the source_type."
        return (text_result.text, None) if text_result.ok else (None, text_result.warning)
    return None, f"Unsupported file type '{ext}' for a text-based source (supported: {', '.join(_SUPPORTED_TEXT_EXTENSIONS)})."


def _extract_records(ext: str, data: bytes) -> tuple[list[dict] | None, str | None]:
    """Returns (records, failure_reason) -- exactly one is non-None."""
    if ext == ".csv":
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace")))
        return list(reader), None
    if ext == ".xlsx":
        result = extract_records_from_xlsx(data)
        return (result.records, None) if result.ok else (None, result.warning)
    if ext == ".json":
        _, records_result = extract_json(data)
        if records_result is None:
            return None, "JSON content is text-shaped, not record-shaped -- check the source_type."
        return (records_result.records, None) if records_result.ok else (None, records_result.warning)
    return None, f"Unsupported file type '{ext}' for a structured source (supported: {', '.join(_SUPPORTED_STRUCTURED_EXTENSIONS)})."


def _process(evidence: Evidence, data: bytes, db: Session) -> None:
    """
    Run the existing, unmodified ingestion pipeline against the raw bytes
    just stored, scoped to the evidence's investigation. Never raises --
    failures are recorded on the Evidence row itself (`processing_status`)
    so a bad upload doesn't 500 the request that registered it.

    TXT/CSV go straight through, exactly as before. PDF/DOCX/XLSX/JSON are
    first converted to text/records by app/ingestion/document_extraction.py
    -- real extraction, and an honest FAILED status (with the real reason,
    e.g. "Scanned document requires OCR processing.") when that extraction
    genuinely can't produce usable content, never a silently-empty success.
    """
    evidence.processing_status = "PROCESSING"
    db.commit()

    store = ScopedGraphStore(get_graph_store(), evidence.investigation_id)
    document_id = f"evidence-{evidence.id}"
    ext = Path(evidence.original_filename).suffix.lower()

    try:
        if evidence.source_type in _TEXT_PIPELINE_SOURCE:
            text, failure = _extract_text(ext, data)
            if failure:
                evidence.processing_status = "FAILED"
                evidence.processing_summary = {"error": failure}
            else:
                result = ingest_text_document(
                    store, _TEXT_PIPELINE_SOURCE[evidence.source_type], document_id, text,
                    metadata={"evidence_id": evidence.id, "original_filename": evidence.original_filename},
                )
                # `result.entities` (real EntityOut rows the unmodified pipeline
                # already returns) lets the upload UI show what KINDS of
                # entities were found, not just a bare count -- entirely
                # derived from real extraction output, nothing invented.
                entity_types: dict[str, int] = {}
                for e in result.entities:
                    entity_types[e.type] = entity_types.get(e.type, 0) + 1
                evidence.processing_summary = {
                    "entities_extracted": result.entities_extracted,
                    "relations_extracted": result.relations_extracted,
                    "entity_types": entity_types,
                }
                evidence.processing_status = "PROCESSED"
        elif evidence.source_type in _STRUCTURED_PIPELINE_SOURCE:
            records, failure = _extract_records(ext, data)
            if failure:
                evidence.processing_status = "FAILED"
                evidence.processing_summary = {"error": failure}
            else:
                summary = ingest_structured(store, _STRUCTURED_PIPELINE_SOURCE[evidence.source_type],
                                             records, document_id)
                evidence.processing_summary = summary.model_dump()
                evidence.processing_status = "PROCESSED"
        else:
            # OTHER: metadata-only registration in Phase 1 -- no known
            # extraction path yet. Left as UPLOADED, not an error.
            evidence.processing_status = "UPLOADED"
            evidence.processing_summary = {"note": "OTHER source_type: metadata registered, not auto-processed."}
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: never let ingestion crash the upload
        evidence.processing_status = "FAILED"
        evidence.processing_summary = {"error": str(exc)}
    db.commit()


@router.post("", response_model=EvidenceOut)
async def upload_evidence(investigation_id: str, case_id: str,
                           source_type: str = Form(...), description: str = Form(""),
                           file: UploadFile = File(...),
                           user: AuthUser = Depends(require_role(*_WRITE_ROLES)),
                           db: Session = Depends(get_db)):
    _require_case(investigation_id, case_id, db)
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

    _process(evidence, data, db)

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
