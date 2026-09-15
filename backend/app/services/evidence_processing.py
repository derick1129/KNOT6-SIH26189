"""
The actual "run this file through the ingestion pipeline" logic, factored
out of `app/api/routes/evidence.py` so it can be replayed from more than one
call site -- the upload endpoint itself, and
`app/services/graph_recovery.py`'s startup rebuild (an investigation's
extracted graph lives only in the in-memory GraphStore, see
app/db/graph_store.py's module docstring, so it has to be reproducible from
the durably-stored Evidence row + raw file bytes whenever that in-memory
state is lost -- a process restart today, a future multi-worker deployment
tomorrow).

Also home to `ensure_not_demo_protected`, the one guard that stops a real
"Add Intelligence" upload from ever being merged into the bundled demo
investigation again (see `Investigation.is_demo_seed`'s docstring in
app/db/models.py and docs/DEMO_DATA.md) -- shared by both the per-case
evidence upload route and the legacy `/ingest/*` routes so there is exactly
one place this rule is enforced, not one copy per call site.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.graph_store import GraphStore, ScopedGraphStore, get_graph_store
from app.db.models import Evidence, Investigation
from app.ingestion.document_extraction import (
    extract_json, extract_records_from_xlsx, extract_text_from_docx, extract_text_from_pdf,
)
from app.services.pipeline import ingest_structured, ingest_text_document

# Evidence.source_type (PS-shaped, per KNOT6 Phase 1 spec) -> the existing
# pipeline's source_type vocabulary (app/api/routes/ingestion.py).
TEXT_PIPELINE_SOURCE = {
    "FIR": "fir", "POLICE_REPORT": "fir", "SURVEILLANCE": "surveillance",
    "SOCIAL_MEDIA": "social_media", "INTELLIGENCE_REPORT": "intel_report",
}
STRUCTURED_PIPELINE_SOURCE = {
    "CDR": "cdr", "FINANCIAL_TRANSACTION": "financial", "CRIMINAL_HISTORY": "criminal_history",
}

SUPPORTED_TEXT_EXTENSIONS = (".txt", ".pdf", ".docx", ".json")
SUPPORTED_STRUCTURED_EXTENSIONS = (".csv", ".xlsx", ".json")


def ensure_not_demo_protected(investigation: Investigation) -> None:
    """
    Refuse to run new intelligence into the bundled demo investigation.

    This is the fix for the incident this module's docstring references:
    "Add Intelligence" always writes into whichever investigation/case is
    currently selected (correctly -- that is the feature), so the one actual
    gap was that nothing stopped a real upload from landing in the demo
    dataset itself. Raising here, at the one shared entry point every
    ingestion route funnels through, closes it for every current and future
    upload path at once rather than relying on UI-only friction.
    """
    if investigation.is_demo_seed:
        raise HTTPException(
            409,
            f"'{investigation.name}' is the protected demo dataset (see docs/DEMO_DATA.md) and "
            "cannot receive new intelligence uploads. Create a new investigation for real casework "
            "-- POST /api/investigations -- and upload there instead.",
        )


def extract_text(ext: str, data: bytes) -> tuple[str | None, str | None]:
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
    return None, f"Unsupported file type '{ext}' for a text-based source (supported: {', '.join(SUPPORTED_TEXT_EXTENSIONS)})."


def extract_records(ext: str, data: bytes) -> tuple[list[dict] | None, str | None]:
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
    return None, f"Unsupported file type '{ext}' for a structured source (supported: {', '.join(SUPPORTED_STRUCTURED_EXTENSIONS)})."


def process_evidence(evidence: Evidence, data: bytes, db: Session,
                      store: GraphStore | None = None) -> None:
    """
    Run the existing, unmodified ingestion pipeline against the raw bytes
    just stored (or being replayed), scoped to the evidence's investigation.
    Never raises -- failures are recorded on the Evidence row itself
    (`processing_status`) so a bad upload doesn't 500 the request that
    registered it, and so a replay (see app/services/graph_recovery.py)
    never crashes the startup it runs during.

    `store` is injectable so a replay can reuse the same
    already-constructed `ScopedGraphStore`; a fresh upload just lets it
    default to the live one for this evidence's investigation.
    """
    evidence.processing_status = "PROCESSING"
    db.commit()

    if store is None:
        store = ScopedGraphStore(get_graph_store(), evidence.investigation_id)
    document_id = f"evidence-{evidence.id}"
    ext = Path(evidence.original_filename).suffix.lower()

    try:
        if evidence.source_type in TEXT_PIPELINE_SOURCE:
            text, failure = extract_text(ext, data)
            if failure:
                evidence.processing_status = "FAILED"
                evidence.processing_summary = {"error": failure}
            else:
                result = ingest_text_document(
                    store, TEXT_PIPELINE_SOURCE[evidence.source_type], document_id, text,
                    metadata={"evidence_id": evidence.id, "original_filename": evidence.original_filename},
                )
                entity_types: dict[str, int] = {}
                for e in result.entities:
                    entity_types[e.type] = entity_types.get(e.type, 0) + 1
                evidence.processing_summary = {
                    "entities_extracted": result.entities_extracted,
                    "relations_extracted": result.relations_extracted,
                    "entity_types": entity_types,
                }
                evidence.processing_status = "PROCESSED"
        elif evidence.source_type in STRUCTURED_PIPELINE_SOURCE:
            records, failure = extract_records(ext, data)
            if failure:
                evidence.processing_status = "FAILED"
                evidence.processing_summary = {"error": failure}
            else:
                summary = ingest_structured(store, STRUCTURED_PIPELINE_SOURCE[evidence.source_type],
                                             records, document_id)
                evidence.processing_summary = summary.model_dump()
                evidence.processing_status = "PROCESSED"
        else:
            # OTHER: metadata-only registration -- no known extraction path yet.
            evidence.processing_status = "UPLOADED"
            evidence.processing_summary = {"note": "OTHER source_type: metadata registered, not auto-processed."}
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: never let ingestion crash the caller
        evidence.processing_status = "FAILED"
        evidence.processing_summary = {"error": str(exc)}
    db.commit()
