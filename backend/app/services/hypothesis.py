"""
Hypothesis Lab persistence: turns the original Hypothesis Lab's live,
client-side analysis (frontend/src/pages/HypothesisLab.tsx composing
`/analytics/influencers`, `/analytics/communities`, `/graph/path`) into a
saved, revisitable investigative record -- while still computing the actual
analytical context (path, centrality, community, signals, timeline) fresh on
every read from those same unmodified analytics modules. See
app/db/models.py:Hypothesis's docstring for why the path/analytics are
deliberately never frozen at save time.

Ethics-language guarantee (KNOT6_PROJECT_SPECIFICATION.pdf's non-negotiable
rule): `narrate_assessment()` below is the ONLY place hypothesis status
gets turned into prose, and it never says a hypothesis "is true" -- only
what the current evidence supports, contradicts, or leaves inconclusive.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.anomaly import run_all_detectors
from app.analytics.centrality import compute_influencers
from app.analytics.community import compute_communities
from app.analytics.pathfinder import find_path
from app.db.graph_store import GraphStore
from app.db.models import Evidence, Hypothesis, HypothesisEvidence
from app.models.schemas import (
    EntityOut, EvidenceOut, HypothesisAnalyticalContext, HypothesisDetailOut,
    HypothesisEvidenceOut, HypothesisNoteOut, HypothesisOut,
)
from app.services.timeline import timeline_for_entities


def _entity_out(node) -> EntityOut | None:
    if node is None:
        return None
    return EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                      source_count=len(node.source_documents))


def _counts(db: Session, hypothesis_id: str) -> tuple[int, int, int]:
    links = db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id == hypothesis_id).all()
    supporting = sum(1 for l in links if l.relationship_type == "SUPPORTING")
    contradicting = sum(1 for l in links if l.relationship_type == "CONTRADICTING")
    return supporting, contradicting, len(links)


def to_summary(db: Session, h: Hypothesis) -> HypothesisOut:
    supporting, contradicting, _ = _counts(db, h.id)
    return HypothesisOut(
        id=h.id, investigation_id=h.investigation_id, case_id=h.case_id, title=h.title,
        description=h.description, status=h.status, subject_entity_id=h.subject_entity_id,
        target_entity_id=h.target_entity_id, related_entity_ids=list(h.related_entity_ids or []),
        supporting_count=supporting, contradicting_count=contradicting, note_count=len(h.notes or []),
        created_by=h.created_by, created_at=h.created_at, updated_at=h.updated_at,
    )


def _build_analytical_context(store: GraphStore, h: Hypothesis) -> HypothesisAnalyticalContext:
    ctx = HypothesisAnalyticalContext()
    subject = store.get_node(h.subject_entity_id) if h.subject_entity_id else None
    target = store.get_node(h.target_entity_id) if h.target_entity_id else None
    ctx.subject_entity = _entity_out(subject)
    ctx.target_entity = _entity_out(target)

    touched_ids: set[str] = set()
    if subject:
        touched_ids.add(subject.id)
    if target:
        touched_ids.add(target.id)
    touched_ids.update(h.related_entity_ids or [])

    if subject:
        influencers = compute_influencers(store, top_n=10_000)
        ctx.subject_influencer = next((i for i in influencers if i.entity.id == subject.id), None)
        if target:
            ctx.target_influencer = next((i for i in influencers if i.entity.id == target.id), None)
            communities = compute_communities(store)
            subj_comm = next((c for c in communities if any(m.id == subject.id for m in c.members)), None)
            tgt_comm = next((c for c in communities if any(m.id == target.id for m in c.members)), None)
            if subj_comm and tgt_comm:
                ctx.same_community = subj_comm.community_id == tgt_comm.community_id
            ctx.path = find_path(store, subject.id, target.id)

    if touched_ids:
        all_signals = run_all_detectors(store)
        ctx.relevant_signals = [s for s in all_signals if touched_ids.intersection(s.entities_involved)]
        ctx.relevant_timeline = timeline_for_entities(store, touched_ids, limit=15)

    return ctx


def narrate_assessment(h: Hypothesis, supporting: int, contradicting: int) -> str:
    """
    The ethics-critical sentence. Never a verdict -- only what the current
    tally of investigator-tagged evidence indicates, explicitly framed as
    provisional and subject to investigator verification.
    """
    if supporting == 0 and contradicting == 0:
        return ("No evidence has been tagged for or against this hypothesis yet. Attach supporting or "
                "contradicting evidence to begin building an evidentiary picture.")
    if supporting > 0 and contradicting == 0:
        return (f"Current evidence supports this hypothesis in {supporting} tagged item"
                f"{'s' if supporting != 1 else ''}, with no contradicting evidence recorded. This is an "
                f"investigative lead, not a determination -- it requires investigator verification.")
    if contradicting > 0 and supporting == 0:
        return (f"Current evidence contradicts this hypothesis in {contradicting} tagged item"
                f"{'s' if contradicting != 1 else ''}, with no supporting evidence recorded.")
    return (f"Current evidence is mixed: {supporting} tagged item{'s' if supporting != 1 else ''} support "
            f"this hypothesis and {contradicting} tagged item{'s' if contradicting != 1 else ''} contradict "
            f"it. This is inconclusive on the tagged evidence alone and requires investigator judgment.")


def to_detail(store: GraphStore, db: Session, h: Hypothesis) -> HypothesisDetailOut:
    summary = to_summary(db, h)

    links = (db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id == h.id)
             .order_by(HypothesisEvidence.created_at.asc()).all())
    evidence_by_id = {
        row.id: row for row in db.query(Evidence).filter(
            Evidence.id.in_([l.evidence_id for l in links])
        ).all()
    } if links else {}

    def _link_out(l: HypothesisEvidence) -> HypothesisEvidenceOut:
        ev = evidence_by_id.get(l.evidence_id)
        return HypothesisEvidenceOut(
            id=l.id, hypothesis_id=l.hypothesis_id, evidence_id=l.evidence_id,
            relationship_type=l.relationship_type, note=l.note, created_by=l.created_by,
            created_at=l.created_at, evidence=EvidenceOut.model_validate(ev) if ev else None,
        )

    supporting_links = [_link_out(l) for l in links if l.relationship_type == "SUPPORTING"]
    contradicting_links = [_link_out(l) for l in links if l.relationship_type == "CONTRADICTING"]

    related_entities = []
    for eid in (h.related_entity_ids or []):
        node = store.get_node(eid)
        if node:
            related_entities.append(_entity_out(node))

    analytical_context = _build_analytical_context(store, h)
    assessment = narrate_assessment(h, len(supporting_links), len(contradicting_links))

    return HypothesisDetailOut(
        **summary.model_dump(),
        notes=[HypothesisNoteOut(**n) for n in (h.notes or [])],
        supporting_evidence=supporting_links,
        contradicting_evidence=contradicting_links,
        related_entities=related_entities,
        analytical_context=analytical_context,
        assessment=assessment,
    )
