"""
Deterministic, no-LLM answering for the common investigative question
shapes KNOT6 Case Intelligence 2.0 calls out explicitly: entity lookup,
entity connections, relationship/path lookup, evidence lookup, investigation
statistics, open signals, "what is happening" summaries, and "where did I
leave off" / "what changed since my last review" (backed by
app/services/activity.py).

This module only *narrates* an already-retrieved `RetrievalBundle` -- the
exact same one app/copilot/copilot.py builds for the LLM path via
app/copilot/retriever.py. It never queries the graph or database itself, so
it can never drift from what the LLM path (or the deterministic /
intelligence summary) would ground an answer in.

`answer_deterministically()` returns `None` when the question needs genuine
open-ended reasoning this layer can't safely attempt -- the caller
(InvestigationCopilot.answer) then sends the honest "AI reasoning is not
configured" message rather than ever fabricating a reply. The one subtlety
that makes this a real guarantee rather than a loophole: rule 7 (the "what
is happening" case-brief fallback) is keyword-gated to actual state
questions -- without that gate, the fact that `bundle.case_brief` is always
populated when no entity is recognized would make this function answer
*every* zero-entity question, including ones that have nothing to do with
investigation state, defeating the "never fake it" guarantee entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.copilot.context_builder import RetrievalBundle, evidence_code
from app.db.graph_store import Node
from app.db.models import CopilotConversationTurn
from app.graph import schema
from app.models.schemas import CopilotCitation, ResumePoint
from app.services.investigation_intelligence import describe_relation

# Relation types that are unconditionally financial for rule 6a below.
# Deliberately NOT including OWNS here: OWNS is generic ownership (a PHONE,
# a VEHICLE, or a FINANCIAL_ACCOUNT), so an OWNS edge only counts as a
# financial connection when the owned node is actually a FINANCIAL_ACCOUNT
# (checked separately, per-edge, below) -- otherwise "his financial
# connections" would wrongly include the phone/vehicle he owns.
_FINANCIAL_RELATION_TYPES = {schema.TRANSACTED_WITH}


@dataclass
class DeterministicAnswer:
    answer: str
    citations: list[CopilotCitation] = field(default_factory=list)


_LEFT_OFF_PHRASES = ("left off", "where did i stop", "where did i leave", "resume", "pick up where", "continue where")
_CHANGED_PHRASES = ("what changed", "what's changed", "since my last", "since last", "what's new since", "whats new since")
_SIGNAL_PHRASES = ("signal", "unusual", "anomal", "suspicious pattern", "flagged")
_FINANCIAL_PHRASES = ("financial", "transaction", "account", "money", "payment")
_TEMPORAL_PHRASES = ("what happened", "around the time", "around this", "meeting", "the event", "timeline")
_VAGUE_CONTINUATION_PHRASES = ("show me those", "show those", "those connections", "these connections",
                                "show me that", "what are those")
_EVIDENCE_PHRASES = ("evidence", "proof", "support", "documented", "sourced")
_STATE_QUESTION_PHRASES = (
    "what is happening", "whats happening", "what's happening", "what is going on", "what's going on",
    "whats going on", "summarize", "summary", "overview", "status of this", "brief me", "give me a brief",
    "tell me about this investigation", "what do we know",
)


def is_standalone_question(question: str) -> bool:
    """
    True when the question is clearly about the investigation as a whole
    (or about resuming/reviewing it) rather than continuing to discuss a
    specific previously-mentioned entity -- "what is happening", "what are
    the open signals", "where did I leave off" never mean "...about the
    entity we were just discussing". InvestigationCopilot.answer() checks
    this BEFORE applying its history-entity fallback: without this guard, a
    standalone question asked right after an entity-focused turn would
    wrongly inherit that entity and get answered as if it were still about
    that entity (see this module's rule ordering below -- entity-focused
    rule 6 is checked before the state-question rule 7).
    """
    q = question.lower()
    return any(p in q for p in _LEFT_OFF_PHRASES + _CHANGED_PHRASES + _SIGNAL_PHRASES + _STATE_QUESTION_PHRASES)


def _cite_tag(ev) -> str:
    return f"[{evidence_code(ev)}]"


def _evidence_citations(evidence, limit: int) -> list[CopilotCitation]:
    return [CopilotCitation(evidence_id=e.id, label=f"{e.original_filename} ({evidence_code(e)})")
            for e in evidence[:limit]]


def answer_deterministically(question: str, entities: list[Node], intent: str, bundle: RetrievalBundle,
                              history: list[CopilotConversationTurn], resume_point: ResumePoint | None,
                              previous_cutoff: datetime | None) -> DeterministicAnswer | None:
    q = question.lower()

    # 1. "Where did I leave off?"
    if any(p in q for p in _LEFT_OFF_PHRASES):
        if resume_point is not None and resume_point.available:
            return DeterministicAnswer(answer=resume_point.description)
        return DeterministicAnswer(
            answer="You haven't reviewed anything in this investigation yet. Ask a question or open an "
                   "entity to get started."
        )

    # 2. "What changed since my last review?" -- copilot.py pre-renders this
    # onto bundle.note (prefixed CHANGED_SINCE:) because only it has the
    # investigation_id/db access needed for get_previous_visit_cutoff; this
    # module only narrates the already-rendered text.
    if bundle.note and bundle.note.startswith("CHANGED_SINCE:"):
        return DeterministicAnswer(answer=bundle.note[len("CHANGED_SINCE:"):].strip())
    if any(p in q for p in _CHANGED_PHRASES):
        # Reached only if copilot.py didn't classify this as RECENT intent
        # (so bundle.note wasn't pre-rendered) -- still honest, just generic.
        return DeterministicAnswer(answer="Nothing has changed in this investigation since your last review.")

    # 2z. Plain RECENT intent (no "since"/"changed" wording) -- copilot.py
    # pre-renders the app-activity feed onto bundle.note (leading with
    # "Recent developments"), same pre-rendered-note pattern as
    # CHANGED_SINCE/HYPOTHESIS above. Without this, a RECENT-classified
    # question with no matching rule below fell all the way through to "AI
    # reasoning is not configured" even though a perfectly good answer was
    # already sitting in bundle.note -- caught by actually asking "what
    # happened recently", not by inspection.
    if bundle.note and bundle.note.startswith("Recent developments"):
        return DeterministicAnswer(answer=bundle.note)

    # 2y. TEMPORAL intent: a mentioned date with no named entity ("what
    # happened around 14 August?") -- narrate the real case timeline
    # copilot.py already retrieved near that date (bundle.timeline), not the
    # app-activity feed.
    if bundle.intent == "TEMPORAL":
        if bundle.timeline:
            lines = [f"Recorded case events near that date ({len(bundle.timeline)} shown):"]
            lines.extend(f"- {t.timestamp.isoformat()}: {t.description}" for t in bundle.timeline)
            return DeterministicAnswer(answer="\n".join(lines))
        return DeterministicAnswer(
            answer=bundle.note or "No timeline events were found near that date in this investigation."
        )

    # 2w. Case-wide evidence question ("What evidence do we have?") --
    # copilot.py pre-renders build_evidence_summary's real, already-used-
    # elsewhere-in-the-app totals onto bundle.note (prefixed
    # EVIDENCE_SUMMARY:), same pattern as the other pre-rendered notes.
    if bundle.note and bundle.note.startswith("EVIDENCE_SUMMARY:"):
        return DeterministicAnswer(answer=bundle.note[len("EVIDENCE_SUMMARY:"):].strip())

    # 2x. COMMUNITIES intent: real detected groupings and which entities
    # bridge more than one of them (app/analytics/community.py, unmodified).
    if bundle.intent == "COMMUNITIES":
        if not bundle.communities:
            return DeterministicAnswer(
                answer="No community structure has been detected in this investigation's graph yet."
            )
        lines = ["Detected community structure:"]
        lines.extend(f"- {c.label} (community #{c.community_id}): {c.size} entities" for c in bundle.communities[:6])
        if bundle.bridge_entities:
            lines.append("Entities connecting multiple communities:")
            lines.extend(f"- {node.label} ({node.type}) touches {count} different communities"
                         for node, count in bundle.bridge_entities[:5])
        else:
            lines.append("No single entity was found bridging multiple communities in the current graph.")
        return DeterministicAnswer(answer="\n".join(lines))

    # 2a. Hypothesis questions ("what evidence contradicts this hypothesis?")
    # -- copilot.py pre-renders the resolved hypothesis's assessment onto
    # bundle.note (prefixed HYPOTHESIS: / HYPOTHESIS_NONE:) because building
    # it needs direct DB access to Hypothesis/HypothesisEvidence this module
    # doesn't have; this only narrates the already-rendered text, same
    # pattern as CHANGED_SINCE above.
    if bundle.note and bundle.note.startswith("HYPOTHESIS_NONE:"):
        return DeterministicAnswer(answer=bundle.note[len("HYPOTHESIS_NONE:"):].strip())
    if bundle.note and bundle.note.startswith("HYPOTHESIS:"):
        text = bundle.note[len("HYPOTHESIS:"):].strip()
        cites: list[CopilotCitation] = []
        if bundle.evidence:
            codes = " ".join(_cite_tag(e) for e in bundle.evidence[:5])
            text += f"\nEvidence: {codes}"
            cites = _evidence_citations(bundle.evidence, 5)
        return DeterministicAnswer(answer=text, citations=cites)

    # 2b. "Who are the most relevant/important entities?" -- ranked
    # influencer list with a concrete, non-guilt "why it matters" reason per
    # entity (degree/betweenness/cross-domain), matching the PS spec's
    # worked example. Only when no specific entity was named: an
    # entity-scoped version of this question is answered by rule 6 below via
    # that entity's own influencer_rank already folded into its narration.
    # Gated on the actual classified INFLUENCERS intent, not merely
    # "bundle.influencers happens to be non-empty" -- the no-entity GENERAL
    # fallback (copilot.py's final `else` branch) also populates a top-5
    # influencers list for other purposes, and reusing that as the trigger
    # here hijacked plain state questions like "what is happening?" into an
    # influencer ranking instead of the case brief (rule 7). Caught by
    # actually asking both questions back to back, not by inspection.
    if bundle.intent == "INFLUENCERS" and not entities and bundle.influencers:
        lines = ["Most relevant entities by investigation-wide network analysis:"]
        for i in bundle.influencers[:5]:
            reasons = []
            if i.betweenness_centrality > 0.05:
                reasons.append("bridges multiple parts of the network")
            if i.degree_centrality > 0.15:
                reasons.append("highly connected")
            if not reasons:
                reasons.append("appears among the most central entities")
            lines.append(f"- #{i.rank} {i.entity.label} ({i.entity.type}) -- {', '.join(reasons)} "
                         f"(composite relevance score {i.composite_score:.3f})")
        return DeterministicAnswer(answer="\n".join(lines))

    # 3. Open signals / "what is unusual" -- only when no specific entity was
    # named (an entity-scoped "unusual" question is handled by rule 6 below,
    # via bundle.signals filtered to that entity already).
    if any(p in q for p in _SIGNAL_PHRASES) and not entities:
        if not bundle.signals:
            return DeterministicAnswer(answer="No open investigative signals have been detected in this investigation.")
        financial_only = any(p in q for p in _FINANCIAL_PHRASES)
        signals = bundle.signals
        lead = "Open investigative signals:"
        if financial_only:
            filtered = [s for s in signals if s.type == "CIRCULAR_TRANSACTION"]
            if not filtered:
                return DeterministicAnswer(answer="No unusual financial activity has been detected in this investigation.")
            signals = filtered
            lead = "Unusual financial activity detected:"
        lines = [f"- [{s.severity.upper()}] {s.type.replace('_', ' ').title()}: {s.description}" for s in signals[:8]]
        return DeterministicAnswer(answer=lead + "\n" + "\n".join(lines))

    # 4. Path questions.
    if bundle.path is not None:
        if not bundle.path.found:
            return DeterministicAnswer(answer="No connection was found between these entities in the current graph.")
        hop_desc = " -> ".join(h.entity.label for h in bundle.path.path)
        text = f"A {bundle.path.hops}-hop path connects them: {hop_desc}."
        cites: list[CopilotCitation] = []
        if bundle.evidence:
            codes = " ".join(_cite_tag(e) for e in bundle.evidence[:3])
            text += f" Supporting evidence: {codes}"
            cites = _evidence_citations(bundle.evidence, 3)
        return DeterministicAnswer(answer=text, citations=cites)

    # 5. Evidence questions with resolved entities (direct mention, or the
    # relaxed history fallback InvestigationCopilot.answer applies when no
    # entities are named in the text but a prior turn resolved some).
    if any(p in q for p in _EVIDENCE_PHRASES) and entities:
        if not bundle.evidence:
            return DeterministicAnswer(
                answer=f"No evidence items currently connect to {entities[0].label} in this investigation."
            )
        codes = " ".join(_cite_tag(e) for e in bundle.evidence[:5])
        names = ", ".join(e.label for e in entities[:2])
        return DeterministicAnswer(
            answer=f"The connection involving {names} is supported by {len(bundle.evidence)} evidence "
                   f"item(s): {codes}",
            citations=_evidence_citations(bundle.evidence, 5),
        )

    # 6a. Entity-focused + financial intent: "what about his financial
    # connections?" must not fall through to the generic top-5 connections
    # list below, which may bury or omit the financial ones entirely --
    # filter the same already-retrieved neighborhood down to
    # TRANSACTED_WITH/OWNS edges (and any edge touching a FINANCIAL_ACCOUNT
    # node) before rule 6's generic narration runs.
    #
    # A bare continuation ("Show me those connections.") carries no topic
    # keyword of its own -- it inherits the PREVIOUS turn's topic by
    # re-checking that turn's question text, not just the entity it
    # resolved to. Without this, "his financial connections" followed by
    # "show me those connections" silently reverted to the generic
    # (non-financial) connection list on the very next turn -- one of the
    # PS's own worked conversational-follow-up examples.
    prior_question = history[-1].question.lower() if history else ""
    financial_intent = any(p in q for p in _FINANCIAL_PHRASES) or (
        any(p in q for p in _VAGUE_CONTINUATION_PHRASES) and any(p in prior_question for p in _FINANCIAL_PHRASES)
    )
    if entities and financial_intent:
        primary = entities[0]
        nb = bundle.neighborhoods.get(primary.id)
        fin_lines: list[str] = []
        if nb:
            nodes, edges = nb
            id_to_node = {n.id: n for n in nodes}
            for e in edges:
                if primary.id not in (e.source, e.target):
                    continue
                other_id = e.target if e.source == primary.id else e.source
                other = id_to_node.get(other_id)
                is_financial = e.type in _FINANCIAL_RELATION_TYPES or (other and other.type == schema.FINANCIAL_ACCOUNT)
                if not is_financial:
                    continue
                fin_lines.append(f"- {primary.label} {describe_relation(e.type, e.weight)} "
                                  f"{other.label if other else other_id}")
        if not fin_lines:
            return DeterministicAnswer(
                answer=f"No financial connections (transactions or account ownership) have been recorded "
                       f"for {primary.label} in this investigation."
            )
        lines = [f"Financial connections for {primary.label}:"] + fin_lines[:5]
        cites: list[CopilotCitation] = []
        if bundle.evidence:
            codes = " ".join(_cite_tag(e) for e in bundle.evidence[:3])
            lines.append(f"Evidence: {codes}")
            cites = _evidence_citations(bundle.evidence, 3)
        return DeterministicAnswer(answer="\n".join(lines), citations=cites)

    # 6. Entity-focused: "why is X important" / "who is X connected to" /
    # "show his other connections" (pronoun already resolved by the time
    # this is called).
    if entities:
        primary = entities[0]
        lines = [f"{primary.label} is an entity of investigative interest in this investigation."]

        # Temporal questions ("what happened around the meeting at X?") lead
        # with the actual chronological record for this entity, when one
        # exists, rather than only the generic connection list below --
        # otherwise a question specifically asking "what happened" got an
        # answer with no events in it at all (caught by asking it against
        # real data, not by inspection).
        if any(p in q for p in _TEMPORAL_PHRASES) and bundle.timeline:
            lines.append(f"Recorded events involving {primary.label} ({len(bundle.timeline)} shown, most recent first):")
            for t in bundle.timeline[:6]:
                lines.append(f"- {t.timestamp.isoformat()}: {t.description}")

        nb = bundle.neighborhoods.get(primary.id)
        if nb:
            nodes, edges = nb
            id_to_label = {n.id: n.label for n in nodes}
            conn_lines = []
            for e in edges:
                if primary.id not in (e.source, e.target):
                    continue
                other = e.target if e.source == primary.id else e.source
                conn_lines.append(f"- {primary.label} {describe_relation(e.type, e.weight)} {id_to_label.get(other, other)}")
                if len(conn_lines) >= 5:
                    break
            if conn_lines:
                lines.append(f"Direct connections ({len(conn_lines)} shown):")
                lines.extend(conn_lines)
            else:
                lines.append("No direct connections have been recorded for this entity yet.")
        if bundle.signals:
            lines.append(f"{len(bundle.signals)} open investigative signal(s) touch this entity -- "
                          f"requires investigator review.")
        cites: list[CopilotCitation] = []
        if bundle.evidence:
            codes = " ".join(_cite_tag(e) for e in bundle.evidence[:3])
            lines.append(f"Evidence: {codes}")
            cites = _evidence_citations(bundle.evidence, 3)
        return DeterministicAnswer(answer="\n".join(lines), citations=cites)

    # 7. No entities, no more specific sub-route matched: only answer with
    # the case brief when the question is actually asking about
    # investigation state -- see the module docstring for why this gate is
    # load-bearing, not decorative.
    if bundle.case_brief is not None and any(p in q for p in _STATE_QUESTION_PHRASES):
        return DeterministicAnswer(answer=bundle.case_brief.summary)

    # 8. Genuinely open-ended -- decline honestly rather than guess.
    return None
