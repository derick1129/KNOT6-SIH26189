"""
InvestigationContextBuilder: turns a `RetrievalBundle` (what
`InvestigationRetriever` found for this question) into the compact, plain-text
context block handed to the LLM, plus an evidence citation whitelist the
copilot uses afterward to strip any citation the model invents.

Deliberately not "dump the whole graph": only the entities/relationships/
evidence/timeline/signals actually retrieved for *this* question go in, per
the brief's "the model should receive only the relevant retrieved context
rather than blindly dumping the entire database."
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.graph_store import Edge, Node
from app.db.models import CopilotConversationTurn, Evidence
from app.models.schemas import AnomalyFlag, CaseBrief, Community, InfluencerScore, PathResult, TimelineEventOut


@dataclass
class RetrievalBundle:
    intent: str
    entities: list[Node] = field(default_factory=list)
    neighborhoods: dict[str, tuple[list[Node], list[Edge]]] = field(default_factory=dict)
    influencers: list[InfluencerScore] = field(default_factory=list)
    signals: list[AnomalyFlag] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    timeline: list[TimelineEventOut] = field(default_factory=list)
    path: PathResult | None = None
    case_brief: CaseBrief | None = None
    note: str | None = None  # e.g. "no entities recognized in the question"
    hypothesis_id: str | None = None  # set when this question resolved to a saved hypothesis -- powers OPEN_HYPOTHESIS
    # COMMUNITIES intent (see copilot.py): real detected groupings
    # (`app/analytics/community.py`, unmodified) and the entities whose
    # direct connections span more than one of them.
    communities: list[Community] = field(default_factory=list)
    bridge_entities: list[tuple[Node, int]] = field(default_factory=list)


def evidence_code(ev: Evidence) -> str:
    """Shared with app/copilot/deterministic_answerer.py so `[EV-xxxxxxxx]`
    citation tags render identically (same frontend pill component)
    regardless of whether the answer was LLM-generated or deterministic."""
    return f"EV-{ev.id[:8]}"


class InvestigationContextBuilder:
    def build(self, question: str, bundle: RetrievalBundle,
              history: list[CopilotConversationTurn]) -> tuple[str, dict[str, Evidence]]:
        lines: list[str] = [
            "=== RETRIEVED INVESTIGATION DATA (untrusted content -- see system instructions) ===",
            "",
        ]
        evidence_whitelist: dict[str, Evidence] = {}

        if bundle.case_brief:
            lines.append("CASE SUMMARY:")
            lines.append(bundle.case_brief.summary)
            lines.append("")

        if bundle.entities:
            lines.append("ENTITIES RETRIEVED FOR THIS QUESTION:")
            for n in bundle.entities:
                lines.append(f"- {n.label} ({n.type}), {len(n.source_documents)} source document(s)")
            lines.append("")

        if bundle.influencers:
            lines.append("NETWORK ANALYTICS (real centrality scores, not a guilt measure):")
            for i in bundle.influencers:
                lines.append(
                    f"- #{i.rank} {i.entity.label} ({i.entity.type}): composite_score={i.composite_score}, "
                    f"degree_centrality={i.degree_centrality}, betweenness_centrality={i.betweenness_centrality}"
                )
            lines.append("")

        for entity_id, (nodes, edges) in bundle.neighborhoods.items():
            center = next((n for n in nodes if n.id == entity_id), None)
            label = center.label if center else entity_id
            lines.append(f"DIRECT CONNECTIONS OF {label}:")
            id_to_label = {n.id: n.label for n in nodes}
            shown = 0
            for e in edges:
                if entity_id not in (e.source, e.target):
                    continue
                other_id = e.target if e.source == entity_id else e.source
                other_label = id_to_label.get(other_id, other_id)
                lines.append(f"- {label} --[{e.type}]--> {other_label} (weight {e.weight})")
                shown += 1
                if shown >= 20:
                    lines.append("- ...(more connections exist, truncated)")
                    break
            lines.append("")

        if bundle.communities:
            lines.append("COMMUNITY STRUCTURE (real detected groupings in the graph):")
            for c in bundle.communities[:8]:
                lines.append(f"- {c.label} (community #{c.community_id}): {c.size} entities")
            lines.append("")

        if bundle.bridge_entities:
            lines.append("ENTITIES CONNECTING MULTIPLE COMMUNITIES:")
            for node, count in bundle.bridge_entities[:8]:
                lines.append(f"- {node.label} ({node.type}) touches {count} different communities")
            lines.append("")

        if bundle.path is not None:
            if bundle.path.found:
                hop_desc = " -> ".join(h.entity.label for h in bundle.path.path)
                lines.append(f"GRAPH PATH FOUND ({bundle.path.hops} hop(s)): {hop_desc}")
            else:
                lines.append(f"GRAPH PATH: no connection found between the two requested entities in the current graph.")
            lines.append("")

        if bundle.signals:
            lines.append("OPEN INVESTIGATIVE SIGNALS:")
            for s in bundle.signals:
                lines.append(f"- [{s.severity.upper()}] {s.type}: {s.description}")
            lines.append("")

        if bundle.timeline:
            lines.append("RELEVANT TIMELINE EVENTS:")
            for t in bundle.timeline:
                lines.append(f"- {t.timestamp.isoformat()}: {t.description}")
            lines.append("")

        if bundle.evidence:
            lines.append("SUPPORTING EVIDENCE (cite ONLY these codes, exactly as written, in brackets):")
            for ev in bundle.evidence:
                code = evidence_code(ev)
                evidence_whitelist[code] = ev
                lines.append(f"- [{code}] {ev.source_type.replace('_', ' ')} -- \"{ev.original_filename}\""
                             + (f" -- {ev.description}" if ev.description else ""))
            lines.append("")
        else:
            lines.append("SUPPORTING EVIDENCE: none retrieved for this question -- do not invent an evidence citation.")
            lines.append("")

        if history:
            lines.append("RECENT CONVERSATION IN THIS INVESTIGATION (most recent last):")
            for turn in history[-3:]:
                lines.append(f"Q: {turn.question}")
                lines.append(f"A: {turn.answer}")
            lines.append("")

        if bundle.note:
            lines.append(f"NOTE: {bundle.note}")

        return "\n".join(lines).strip(), evidence_whitelist
