"""
Deterministic Case Intelligence: the "what is happening in this
investigation" summary, computed entirely from data the app already has --
the scoped graph (entities/relationships), the analytics engine
(app/analytics/*.py, unmodified), PostgreSQL (Evidence, audit log), and the
timeline projection (app/services/timeline.py).

Deliberately has no LLM dependency: per the KNOT6 Case Intelligence brief,
"a deterministic case summary/search should still work without an LLM" --
this module is that guarantee. app/copilot/copilot.py calls into the same
functions to ground its answers, so the copilot and the summary page can
never disagree about what the investigation actually contains.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.anomaly import run_all_detectors
from app.analytics.centrality import compute_influencers
from app.db.graph_store import GraphStore
from app.db.models import Evidence
from app.graph import schema
from app.models.schemas import (
    CaseBrief, EntityOut, EvidenceOut, EvidenceSummaryOut, IntelligenceSummary,
    InvestigatorNotesOut, KeyEntity, KeyRelationship, OpenSignal, RecentDevelopment,
)
from app.services import audit
from app.services.timeline import build_timeline

# Node type -> the plain-language "domain" it represents in the case brief.
# Only types that actually appear with at least one edge count toward the
# brief's "spanning X, Y and Z activity" sentence -- nothing here is assumed
# present just because the type exists in the schema.
_DOMAIN_BY_TYPE: dict[str, str] = {
    schema.PHONE: "communication",
    schema.FINANCIAL_ACCOUNT: "financial",
    schema.ORGANIZATION: "organizational",
    schema.LOCATION: "geographic",
    schema.VEHICLE: "transportation",
}

_RELATION_VERB = {
    schema.CALLED: "called",
    schema.TRANSACTED_WITH: "transacted with",
    schema.ASSOCIATED_WITH: "is associated with",
    schema.OWNS: "owns",
    schema.PRESENT_AT: "was present at",
    schema.MEMBER_OF: "is a member of",
    schema.MENTIONED_WITH: "was co-mentioned with",
    schema.LINKED_TO_CASE: "is linked to case",
    schema.AUTHORED: "authored",
}

_AUDIT_ACTION_TEXT = {
    "CREATE_INVESTIGATION": "Investigation created.",
    "UPDATE_INVESTIGATION": "Investigation details updated.",
    "ARCHIVE_INVESTIGATION": "Investigation archived.",
    "CREATE_CASE": "New case opened.",
    "UPDATE_CASE": "Case details updated.",
    "CLOSE_CASE": "Case closed.",
    "ARCHIVE_CASE": "Case archived.",
    "UPLOAD_EVIDENCE": "New evidence uploaded.",
    "MERGE_ENTITIES": "Entity resolved (two records merged into one).",
}


def describe_relation(rel_type: str, weight: float) -> str:
    verb = _RELATION_VERB.get(rel_type, rel_type.replace("_", " ").lower())
    if rel_type in (schema.CALLED, schema.TRANSACTED_WITH):
        count = max(1, round(weight))
        noun = "call" if rel_type == schema.CALLED else "transaction"
        return f"{verb} ({count} {noun}{'s' if count != 1 else ''} recorded)"
    return verb


def build_case_brief(store: GraphStore) -> CaseBrief:
    nodes = store.all_nodes()
    edges = store.all_edges()

    if not nodes:
        return CaseBrief(
            summary="No entities or relationships have been ingested into this investigation yet. "
                    "Upload evidence to begin building its intelligence picture.",
            total_entities=0, total_relations=0, cross_domain_entities=0, open_signal_count=0, domains=[],
        )

    # Which domains actually have connected entities of that type.
    node_by_id = {n.id: n for n in nodes}
    domain_present: set[str] = set()
    neighbor_types: dict[str, set[str]] = {n.id: set() for n in nodes}
    for e in edges:
        src, dst = node_by_id.get(e.source), node_by_id.get(e.target)
        if src:
            neighbor_types[e.source].add(dst.type if dst else "")
            if src.type in _DOMAIN_BY_TYPE:
                domain_present.add(_DOMAIN_BY_TYPE[src.type])
        if dst:
            neighbor_types[e.target].add(src.type if src else "")
            if dst.type in _DOMAIN_BY_TYPE:
                domain_present.add(_DOMAIN_BY_TYPE[dst.type])

    # An entity has "cross-domain connections" when its direct neighbors
    # span more than one of the domain categories above (e.g. a person
    # connected to both a PHONE and a FINANCIAL_ACCOUNT).
    cross_domain_count = 0
    for n in nodes:
        domains_touched = {_DOMAIN_BY_TYPE[t] for t in neighbor_types.get(n.id, set()) if t in _DOMAIN_BY_TYPE}
        if len(domains_touched) >= 2:
            cross_domain_count += 1

    signal_count = len(run_all_detectors(store))

    domains = sorted(domain_present)
    if domains:
        if len(domains) == 1:
            span = f"{domains[0]} activity"
        elif len(domains) == 2:
            span = f"{domains[0]} and {domains[1]} activity"
        else:
            span = f"{', '.join(domains[:-1])} and {domains[-1]} activity"
        sentence1 = f"This investigation contains a connected network spanning {span}."
    else:
        sentence1 = "This investigation contains a connected network of entities and relationships."

    sentence2 = f"{len(nodes)} entities and {len(edges)} relationships are currently associated with the investigation."

    if cross_domain_count > 0 and signal_count > 0:
        sentence3 = (f"{cross_domain_count} entit{'y has' if cross_domain_count == 1 else 'ies have'} "
                     f"cross-domain connections and {signal_count} investigative signal"
                     f"{'s' if signal_count != 1 else ''} currently require{'s' if signal_count == 1 else ''} review.")
    elif cross_domain_count > 0:
        sentence3 = (f"{cross_domain_count} entit{'y has' if cross_domain_count == 1 else 'ies have'} "
                     f"cross-domain connections. No investigative signals currently require review.")
    elif signal_count > 0:
        sentence3 = (f"{signal_count} investigative signal{'s' if signal_count != 1 else ''} "
                     f"currently require{'s' if signal_count == 1 else ''} review.")
    else:
        sentence3 = "No cross-domain connections or investigative signals have been detected yet."

    return CaseBrief(
        summary=f"{sentence1}\n\n{sentence2} {sentence3}",
        total_entities=len(nodes), total_relations=len(edges),
        cross_domain_entities=cross_domain_count, open_signal_count=signal_count, domains=domains,
    )


def build_key_entities(store: GraphStore, top_n: int = 5) -> list[KeyEntity]:
    influencers = compute_influencers(store, top_n=top_n)
    if not influencers:
        return []
    max_score = max(i.composite_score for i in influencers) or 1.0
    results = []
    for i in influencers:
        nodes, edges = store.neighbors(i.entity.id, hops=1)
        connections = len(nodes) - 1 if nodes else 0
        ratio = i.composite_score / max_score if max_score else 0.0
        if ratio >= 0.66:
            label = "High investigation relevance"
        elif ratio >= 0.33:
            label = "Moderate investigative interest"
        else:
            label = "Entity of investigative interest -- requires investigator review"
        results.append(KeyEntity(
            entity=i.entity, connections=max(connections, 0),
            relevance_label=label, relevance_score=i.composite_score,
        ))
    return results


def build_key_relationships(store: GraphStore, key_entity_ids: list[str], limit: int = 6) -> list[KeyRelationship]:
    edges = store.all_edges()
    if not edges:
        return []
    key_set = set(key_entity_ids)

    # Prefer edges that touch at least one key entity (most investigatively
    # meaningful); fall back to the highest-weight edges overall so small
    # graphs without a ranked influencer still show something real.
    scored = sorted(edges, key=lambda e: (e.source in key_set or e.target in key_set, e.weight), reverse=True)

    results = []
    seen_pairs = set()
    for e in scored:
        pair = frozenset((e.source, e.target, e.type))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        src, dst = store.get_node(e.source), store.get_node(e.target)
        if not src or not dst:
            continue
        src_out = EntityOut(id=src.id, type=src.type, label=src.label, attributes=src.attributes,
                             source_count=len(src.source_documents))
        dst_out = EntityOut(id=dst.id, type=dst.type, label=dst.label, attributes=dst.attributes,
                             source_count=len(dst.source_documents))
        results.append(KeyRelationship(
            source=src_out, target=dst_out, type=e.type,
            description=describe_relation(e.type, e.weight), evidence=list(e.evidence),
        ))
        if len(results) >= limit:
            break
    return results


def build_recent_developments(investigation_id: str, limit: int = 8) -> list[RecentDevelopment]:
    entries = audit.list_entries(limit=limit, investigation_id=investigation_id)
    out = []
    for entry in entries:
        text = _AUDIT_ACTION_TEXT.get(entry.action)
        if text is None:
            if entry.action.startswith("INGEST_"):
                text = "New evidence ingested."
            else:
                text = entry.action.replace("_", " ").capitalize() + "."
        out.append(RecentDevelopment(
            id=entry.id, kind=entry.action, description=text, timestamp=entry.timestamp, target=entry.target,
        ))
    return out


def build_open_signals(store: GraphStore, limit: int = 8) -> list[OpenSignal]:
    flags = run_all_detectors(store)
    out = []
    for f in flags[:limit]:
        out.append(OpenSignal(
            id=f.id, type=f.type, severity=f.severity, description=f.description,
            entities_involved=list(f.entities_involved),
            primary_entity_id=f.entities_involved[0] if f.entities_involved else None,
        ))
    return out


def build_evidence_summary(db: Session, investigation_id: str, recent_limit: int = 5) -> EvidenceSummaryOut:
    rows = (db.query(Evidence).filter(Evidence.investigation_id == investigation_id)
            .order_by(Evidence.uploaded_at.desc()).all())
    total = len(rows)
    processed = sum(1 for r in rows if r.processing_status == "PROCESSED")
    failed = sum(1 for r in rows if r.processing_status == "FAILED")
    pending = total - processed - failed
    return EvidenceSummaryOut(
        total=total, processed=processed, pending=pending, failed=failed,
        integrity_verified=None,  # Phase 4 scope -- not yet tracked, deliberately not fabricated.
        recent=[EvidenceOut.model_validate(r) for r in rows[:recent_limit]],
    )


def build_investigator_notes() -> InvestigatorNotesOut:
    """
    No notes/hypothesis persistence exists yet (Hypothesis Lab composes its
    output client-side from live analytics, see frontend/src/pages/
    HypothesisLab.tsx -- it has no database table to read from here). Per
    the brief: don't build a notes system as part of this task, just say so
    plainly and keep the shape ready for when one exists.
    """
    return InvestigatorNotesOut(
        available=False, notes=[],
        message="No investigator notes/hypothesis system is persisted yet -- Hypothesis Lab results "
                "are computed live and not saved. This section will populate once notes are stored.",
    )


def build_intelligence_summary(store: GraphStore, db: Session, investigation_id: str) -> IntelligenceSummary:
    case_brief = build_case_brief(store)
    key_entities = build_key_entities(store, top_n=5)
    key_relationships = build_key_relationships(store, [k.entity.id for k in key_entities], limit=6)
    recent_developments = build_recent_developments(investigation_id, limit=8)
    open_signals = build_open_signals(store, limit=8)
    evidence_summary = build_evidence_summary(db, investigation_id, recent_limit=5)
    timeline_summary = build_timeline(store, limit=8)
    investigator_notes = build_investigator_notes()

    return IntelligenceSummary(
        investigation_id=investigation_id, case_brief=case_brief, key_entities=key_entities,
        key_relationships=key_relationships, recent_developments=recent_developments,
        open_signals=open_signals, evidence_summary=evidence_summary,
        timeline_summary=timeline_summary, investigator_notes=investigator_notes,
    )
