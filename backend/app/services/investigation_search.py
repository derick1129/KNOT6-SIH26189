"""
Universal, investigation-scoped search: "where is this information?" across
every real data source KNOT6 already has for an investigation -- entities
(the scoped graph), relationships, evidence metadata (PostgreSQL), the
timeline projection, open analytics signals, and the asking user's own
conversation history with the copilot.

Deliberately a plain multi-source fan-out over existing stores, not a search
index -- "practical", per the brief, not "an over-engineered RAG platform".
`app/copilot/retriever.py` calls the same entity/evidence primitives so
search and the AI copilot never disagree about what exists.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.analytics.anomaly import run_all_detectors
from app.db.graph_store import GraphStore
from app.db.models import CopilotConversationTurn, Evidence, Hypothesis
from app.models.schemas import (
    EntityOut, EvidenceOut, KeyRelationship, OpenSignal, SearchConversationHit, SearchEntityHit,
    SearchEvidenceHit, SearchHypothesisHit, SearchRelationshipHit, SearchResults, SearchTimelineHit,
)
from app.services.investigation_intelligence import describe_relation
from app.services.timeline import build_timeline


def _entity_out(node) -> EntityOut:
    return EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                      source_count=len(node.source_documents))


def search_investigation(store: GraphStore, db: Session, investigation_id: str, username: str,
                          q: str, limit: int = 8) -> SearchResults:
    q_norm = q.strip().lower()
    results = SearchResults(query=q)
    if not q_norm:
        return results

    # --- Entities -----------------------------------------------------
    matches = store.search_nodes(q, limit=limit)
    matched_ids = {n.id for n in matches}
    for n in matches:
        nodes, _ = store.neighbors(n.id, hops=1)
        connections = max(len(nodes) - 1, 0) if nodes else 0
        results.entities.append(SearchEntityHit(entity=_entity_out(n), connections=connections))

    # --- Related entities (1-hop neighborhood of the best match) ------
    if matches:
        nodes, _ = store.neighbors(matches[0].id, hops=1)
        related = [n for n in nodes if n.id != matches[0].id][:8]
        results.related_entities = [_entity_out(n) for n in related]

    # --- Relationships (touch a matched entity, or mention q directly) --
    all_edges = store.all_edges()
    rel_count = 0
    for e in all_edges:
        if rel_count >= limit:
            break
        if not (e.source in matched_ids or e.target in matched_ids or q_norm in e.type.lower()):
            continue
        src, dst = store.get_node(e.source), store.get_node(e.target)
        if not src or not dst:
            continue
        results.relationships.append(SearchRelationshipHit(relationship=KeyRelationship(
            source=_entity_out(src), target=_entity_out(dst), type=e.type,
            description=describe_relation(e.type, e.weight), evidence=list(e.evidence),
        )))
        rel_count += 1

    # --- Evidence: metadata match, or referenced by a matched entity ---
    evidence_ids_from_entities: set[str] = set()
    for e in all_edges:
        if e.source in matched_ids or e.target in matched_ids:
            evidence_ids_from_entities.update(e.evidence)
    # Evidence rows are registered as f"evidence-{Evidence.id}" document ids
    # by app/api/routes/evidence.py's _process(); strip that prefix to get
    # back the real Evidence primary key for a DB lookup.
    referenced_pks = {ref[len("evidence-"):] for ref in evidence_ids_from_entities if ref.startswith("evidence-")}

    ev_query = db.query(Evidence).filter(Evidence.investigation_id == investigation_id)
    text_filter = or_(
        Evidence.original_filename.ilike(f"%{q}%"),
        Evidence.description.ilike(f"%{q}%"),
        Evidence.source_type.ilike(f"%{q}%"),
    )
    text_matches = ev_query.filter(text_filter).order_by(Evidence.uploaded_at.desc()).limit(limit).all()
    seen_evidence_ids = {r.id for r in text_matches}
    ref_matches = []
    if referenced_pks:
        ref_matches = (db.query(Evidence)
                       .filter(Evidence.investigation_id == investigation_id, Evidence.id.in_(referenced_pks))
                       .order_by(Evidence.uploaded_at.desc()).all())
    for row in (text_matches + [r for r in ref_matches if r.id not in seen_evidence_ids])[:limit]:
        results.evidence.append(SearchEvidenceHit(evidence=EvidenceOut.model_validate(row)))

    # --- Timeline: events touching a matched entity --------------------
    if matched_ids:
        events = [e for e in build_timeline(store, limit=200) if matched_ids.intersection(e.entities_involved)]
    else:
        events = []
    for ev in events[:limit]:
        results.timeline.append(SearchTimelineHit(event=ev))

    # --- Signals: description mentions q, or involves a matched entity --
    for flag in run_all_detectors(store):
        if len(results.signals) >= 5:
            break
        if q_norm in flag.description.lower() or matched_ids.intersection(flag.entities_involved):
            results.signals.append(OpenSignal(
                id=flag.id, type=flag.type, severity=flag.severity, description=flag.description,
                entities_involved=list(flag.entities_involved),
                primary_entity_id=flag.entities_involved[0] if flag.entities_involved else None,
            ))

    # --- Conversation history: this user's own turns in this investigation --
    convo_matches = (
        db.query(CopilotConversationTurn)
        .filter(CopilotConversationTurn.investigation_id == investigation_id,
                CopilotConversationTurn.username == username,
                or_(CopilotConversationTurn.question.ilike(f"%{q}%"),
                    CopilotConversationTurn.answer.ilike(f"%{q}%")))
        .order_by(CopilotConversationTurn.created_at.desc())
        .limit(5)
        .all()
    )
    for turn in convo_matches:
        results.conversation.append(SearchConversationHit(
            turn_id=turn.id, question=turn.question, created_at=turn.created_at,
        ))

    # --- Hypotheses: title/description text match -----------------------
    from app.db.models import HypothesisEvidence  # local import: avoids a module-level cycle with services.hypothesis

    hyp_matches = (
        db.query(Hypothesis)
        .filter(Hypothesis.investigation_id == investigation_id,
                or_(Hypothesis.title.ilike(f"%{q}%"), Hypothesis.description.ilike(f"%{q}%")))
        .order_by(Hypothesis.updated_at.desc())
        .limit(limit)
        .all()
    )
    for h in hyp_matches:
        links = db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id == h.id).all()
        results.hypotheses.append(SearchHypothesisHit(
            id=h.id, title=h.title, status=h.status,
            supporting_count=sum(1 for l in links if l.relationship_type == "SUPPORTING"),
            contradicting_count=sum(1 for l in links if l.relationship_type == "CONTRADICTING"),
        ))

    return results
