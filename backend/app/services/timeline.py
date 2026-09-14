"""
Timeline aggregation: turns event-level data already recorded across the
system -- graph edges (CALLED/TRANSACTED_WITH `events`, plus any edge's
`document_date` attribute -- see app/db/graph_store.py's `record_edge_event`
and app/services/pipeline.py's document-date stamping), evidence
registration (PostgreSQL `evidence.uploaded_at`), and case/investigation
lifecycle actions (the audit log) -- into one chronological feed.

Deliberately a read-only projection over data that already exists -- no new
event storage, no invented timestamps. If a source genuinely has no
timestamp (e.g. some evidence rows, or graph edges with no dated event
recorded), it's simply not included as a timeline point rather than assigned
a fabricated one; `build_investigation_timeline`'s `undated_evidence` return
value surfaces those items separately instead of silently dropping them.

Two entry points:
  - `build_timeline`/`timeline_for_entities` (unchanged signatures): the
    original graph-edges-only projection, still used by the Case
    Intelligence summary and the copilot retriever/search -- untouched so
    those call sites keep working exactly as before.
  - `build_investigation_timeline`: the fuller aggregation (adds evidence
    registration + case/investigation lifecycle events, plus filtering) for
    the dedicated `GET /api/investigations/{id}/timeline` endpoint and the
    upgraded Timeline page.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.graph_store import GraphStore
from app.db.models import Evidence
from app.graph import schema
from app.models.schemas import TimelineEventOut
from app.services import audit

_CASE_EVENT_ACTIONS = {
    "CREATE_INVESTIGATION": "Investigation created",
    "ARCHIVE_INVESTIGATION": "Investigation archived",
    "CREATE_CASE": "Case opened",
    "UPDATE_CASE": "Case updated",
    "CLOSE_CASE": "Case closed",
    "ARCHIVE_CASE": "Case archived",
    "MERGE_ENTITIES": "Entities resolved (merged)",
    "CREATE_HYPOTHESIS": "Hypothesis created",
    "UPDATE_HYPOTHESIS": "Hypothesis updated",
}


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _events_from_graph(store: GraphStore) -> list[TimelineEventOut]:
    g = store.to_networkx()
    events: list[TimelineEventOut] = []

    for u, v, k, d in g.edges(keys=True, data=True):
        etype = d.get("type")
        src, dst = store.get_node(u), store.get_node(v)
        src_label, dst_label = src.label if src else u, dst.label if dst else v
        rel_id = k  # the multigraph edge key IS the real Edge.id -- see GraphStore.all_edges()

        if etype == schema.CALLED:
            for ev in d.get("events", []):
                ts = _parse_dt(ev.get("timestamp"))
                if not ts:
                    continue
                duration = ev.get("duration_seconds")
                desc = f"{src_label} called {dst_label}"
                if duration is not None:
                    desc += f" ({duration}s)"
                events.append(TimelineEventOut(
                    id=str(uuid.uuid4()), timestamp=ts, kind="CALL", title="Call", description=desc,
                    entities_involved=[u, v], relationship_ids=[rel_id], evidence=list(d.get("evidence", [])),
                    source="CDR", metadata={"duration_seconds": duration} if duration is not None else {},
                ))
        elif etype == schema.TRANSACTED_WITH:
            for ev in d.get("events", []):
                ts = _parse_dt(ev.get("timestamp"))
                if not ts:
                    continue
                amount = ev.get("amount")
                desc = f"{src_label} transferred funds to {dst_label}"
                if amount is not None:
                    desc += f" (amount {amount})"
                events.append(TimelineEventOut(
                    id=str(uuid.uuid4()), timestamp=ts, kind="TRANSACTION", title="Transaction", description=desc,
                    entities_involved=[u, v], relationship_ids=[rel_id], evidence=list(d.get("evidence", [])),
                    source="FINANCIAL_TRANSACTION", metadata={"amount": amount} if amount is not None else {},
                ))
        else:
            doc_date = d.get("attributes", {}).get("document_date")
            ts = _parse_dt(doc_date)
            if ts:
                verb = etype.replace("_", " ").lower() if etype else "related to"
                events.append(TimelineEventOut(
                    id=str(uuid.uuid4()), timestamp=ts, kind="PRESENCE", title=etype or "Presence",
                    description=f"{src_label} {verb} {dst_label}",
                    entities_involved=[u, v], relationship_ids=[rel_id], evidence=list(d.get("evidence", [])),
                    source="DOCUMENT",
                ))

    return events


def _undated_relations(store: GraphStore) -> list[dict]:
    """
    Relations that carry no parseable date (no CALL/TRANSACTION event
    timestamp, no `document_date` attribute) -- real relationships that
    simply can't be placed on a timeline, surfaced honestly instead of
    silently dropped or given a fabricated date. Plain dicts, not
    `TimelineEventOut`, since that schema requires a real timestamp.
    """
    g = store.to_networkx()
    undated: list[dict] = []
    for u, v, k, d in g.edges(keys=True, data=True):
        etype = d.get("type")
        if etype == schema.CALLED or etype == schema.TRANSACTED_WITH:
            if d.get("events"):  # has at least one dated event already
                continue
        elif _parse_dt(d.get("attributes", {}).get("document_date")):
            continue
        src, dst = store.get_node(u), store.get_node(v)
        undated.append({
            "relationship_id": k, "type": etype,
            "description": f"{src.label if src else u} {(etype or '').replace('_', ' ').lower()} {dst.label if dst else v}",
            "entities_involved": [u, v], "evidence": list(d.get("evidence", [])),
        })
    return undated


def build_timeline(store: GraphStore, limit: int = 50) -> list[TimelineEventOut]:
    """Original, unchanged behavior: graph-edge events only, newest first."""
    events = _events_from_graph(store)
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:limit]


def timeline_for_entities(store: GraphStore, entity_ids: set[str], limit: int = 20) -> list[TimelineEventOut]:
    """Same feed, filtered to events touching a specific set of entities -- used by the copilot
    retriever when a question names specific entities rather than asking about the whole case."""
    full = _events_from_graph(store)
    full.sort(key=lambda e: e.timestamp, reverse=True)
    filtered = [e for e in full if entity_ids.intersection(e.entities_involved)]
    return filtered[:limit]


def _evidence_events(db: Session, investigation_id: str) -> list[TimelineEventOut]:
    rows = db.query(Evidence).filter(Evidence.investigation_id == investigation_id).all()
    events = []
    for r in rows:
        events.append(TimelineEventOut(
            id=f"evidence-registered-{r.id}", timestamp=r.uploaded_at, kind="EVIDENCE_UPLOADED",
            title="Evidence registered",
            description=f"{r.original_filename} ({r.source_type.replace('_', ' ').lower()}) registered by {r.uploaded_by}",
            entities_involved=[], relationship_ids=[], evidence=[r.id],
            source="EVIDENCE_REGISTRATION",
            metadata={"processing_status": r.processing_status, "source_type": r.source_type},
        ))
    return events


def _case_events(investigation_id: str) -> list[TimelineEventOut]:
    entries = audit.list_entries(limit=500, investigation_id=investigation_id)
    events = []
    for e in entries:
        label = _CASE_EVENT_ACTIONS.get(e.action)
        if not label:
            continue
        events.append(TimelineEventOut(
            id=f"audit-{e.id}", timestamp=e.timestamp, kind="CASE_EVENT", title=label,
            description=f"{label} by {e.actor}" + (f" ({e.target})" if e.target else ""),
            entities_involved=[], relationship_ids=[], evidence=[],
            source="AUDIT_LOG", metadata={"action": e.action, "actor": e.actor},
        ))
    return events


def build_investigation_timeline(
    store: GraphStore, db: Session, investigation_id: str,
    event_types: set[str] | None = None, entity_id: str | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
    ascending: bool = True,
) -> tuple[list[TimelineEventOut], list[dict]]:
    """
    The full aggregation backing `GET /api/investigations/{id}/timeline`.
    Returns `(dated_events, undated_relations)` -- relations that carry no
    reliable timestamp (see `_undated_relations`) are kept available
    separately rather than either dropped or assigned a fabricated date, per
    the "don't invent timestamps" rule. Every `Evidence` row always has a
    real `uploaded_at` (a DB-assigned registration timestamp, not one
    extracted from document content), so evidence itself is never in the
    undated set -- only graph relationships whose source document carried no
    usable date can land there.
    """
    events = _events_from_graph(store) + _evidence_events(db, investigation_id) + _case_events(investigation_id)

    if event_types:
        events = [e for e in events if e.kind in event_types]
    if entity_id:
        events = [e for e in events if entity_id in e.entities_involved]
    if date_from:
        events = [e for e in events if e.timestamp >= date_from]
    if date_to:
        events = [e for e in events if e.timestamp <= date_to]

    events.sort(key=lambda e: e.timestamp, reverse=not ascending)

    undated = _undated_relations(store)
    if entity_id:
        undated = [u for u in undated if entity_id in u["entities_involved"]]
    if event_types and "PRESENCE" not in event_types:
        undated = []  # caller explicitly filtered to kinds that don't include undated relations

    return events, undated
