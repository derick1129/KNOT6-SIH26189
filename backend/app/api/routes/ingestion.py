"""
Ingestion endpoints -- one per PS-named source category. All are
`investigator`/`analyst`/`admin` accessible (read-heavy roles like a
future "viewer" role would be excluded), and every call is audit-logged
with the acting user and the document id, per the PS's implicit
evidentiary requirements.
"""
from __future__ import annotations

import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_store, require_role
from app.core.security import AuthUser
from app.db.graph_store import GraphStore
from app.models.schemas import BulkIngestSummary, IngestResult, TextIngestRequest
from app.services import audit
from app.services.pipeline import ingest_structured, ingest_text_document

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_TEXT_SOURCES = {"fir", "surveillance", "social_media", "intel_report"}
_STRUCTURED_SOURCES = {"cdr", "financial", "criminal_history"}


@router.post("/text", response_model=IngestResult)
def ingest_text(payload: TextIngestRequest,
                 user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                 store: GraphStore = Depends(get_store)):
    if payload.source_type not in _TEXT_SOURCES:
        raise HTTPException(400, f"source_type must be one of {sorted(_TEXT_SOURCES)}")
    result = ingest_text_document(store, payload.source_type, payload.document_id, payload.text, payload.metadata)
    audit.log(actor=user.username, action=f"INGEST_TEXT:{payload.source_type}", target=payload.document_id,
              details={"entities": result.entities_extracted, "relations": result.relations_extracted})
    return result


@router.post("/csv/{source_type}", response_model=BulkIngestSummary)
async def ingest_csv(source_type: str, file: UploadFile = File(...),
                      user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                      store: GraphStore = Depends(get_store)):
    if source_type not in _STRUCTURED_SOURCES:
        raise HTTPException(400, f"source_type must be one of {sorted(_STRUCTURED_SOURCES)}")
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    records = list(reader)
    if not records:
        raise HTTPException(400, "CSV had no data rows.")

    document_id = f"{source_type}-{file.filename}-{uuid.uuid4().hex[:6]}"
    summary = ingest_structured(store, source_type, records, document_id)
    audit.log(actor=user.username, action=f"INGEST_CSV:{source_type}", target=document_id,
              details=summary.model_dump())
    return summary


@router.post("/social-media", response_model=BulkIngestSummary)
async def ingest_social_media(file: UploadFile = File(...),
                               user: AuthUser = Depends(require_role("investigator", "analyst", "admin")),
                               store: GraphStore = Depends(get_store)):
    """
    JSON array of {author, text, timestamp, platform}. Each post is run
    through the same NLP pipeline as an FIR; the author is additionally
    linked to every entity mentioned via an AUTHORED-context edge so
    "who talked about whom" stays visible even when the author itself
    wasn't named inside the post text.
    """
    raw = json.loads((await file.read()).decode("utf-8-sig"))
    if not isinstance(raw, list):
        raise HTTPException(400, "Expected a JSON array of posts.")

    total_entities = total_relations = 0
    document_id = f"social-{file.filename}-{uuid.uuid4().hex[:6]}"
    for i, post in enumerate(raw):
        text = post.get("text", "")
        if not text:
            continue
        result = ingest_text_document(
            store, "social_media", f"{document_id}#{i}", text,
            metadata={"document_date": post.get("timestamp"), "platform": post.get("platform"),
                      "author": post.get("author")},
        )
        total_entities += result.entities_extracted
        total_relations += result.relations_extracted

    audit.log(actor=user.username, action="INGEST_SOCIAL_MEDIA", target=document_id,
              details={"posts": len(raw), "entities": total_entities})
    return BulkIngestSummary(documents_processed=len(raw), records_processed=len(raw),
                              entities_created=total_entities, entities_merged=0,
                              relations_created=total_relations)
