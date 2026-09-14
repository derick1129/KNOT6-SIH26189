"""
InvestigationRetriever: every real data source the copilot is allowed to
read from, in one place, so `copilot.py` never queries the graph or the
database directly. Everything here composes existing, unmodified engines --
`app/analytics/*.py`, `app/db/graph_store.py`, `app/services/timeline.py` --
the same ones Case Intelligence's deterministic summary and the frontend's
own screens already use, so the copilot's grounding can never drift from
what an investigator sees elsewhere in the app.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.analytics.anomaly import run_all_detectors
from app.analytics.centrality import compute_influencers
from app.analytics.community import compute_communities
from app.analytics.pathfinder import find_path
from app.db.graph_store import GraphStore, Node
from app.db.models import Evidence
from app.models.schemas import AnomalyFlag, Community, InfluencerScore, PathResult, TimelineEventOut
from app.services.timeline import build_timeline, timeline_for_entities

# Proper-noun-ish phrases ("Suresh Yadav") and alphanumeric identifiers
# ("ACC1001", a bare phone number) -- the two shapes entity labels take in
# the demo dataset and in any FIR/CDR/financial ingest. Heuristic, not NLP:
# good enough to seed a real graph lookup, and every candidate is verified
# against real entity labels below before it's ever treated as a match.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b")
_ALNUM_ID_RE = re.compile(r"\b[A-Za-z]{2,}\d{2,}\b")
_DIGIT_ID_RE = re.compile(r"\b\d{6,}\b")

_STOPWORD_PHRASES = {"what", "why", "who", "how", "show", "which", "does", "did", "is", "are"}

# A small "did the investigator mention a date" heuristic -- a month name
# plus an optional day number, in either order ("14 August" or "August
# 14"). No year (this demo's data lives in one year) and deliberately not a
# full calendar-parsing dependency: good enough to route a temporal
# question ("what happened around 14 August?") to the investigation's own
# timeline near that date instead of the unrelated app-activity feed
# RECENT-intent questions otherwise use (see copilot.py).
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_DATE_HINT_RE = re.compile(
    r"\b(\d{1,2})?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*(\d{1,2})?\b",
    re.IGNORECASE,
)


def extract_date_hint(text: str) -> tuple[int, int | None] | None:
    """Returns (month, day) -- day is None when only a month was mentioned."""
    m = _DATE_HINT_RE.search(text)
    if not m:
        return None
    month = _MONTHS.get(m.group(2).lower())
    if month is None:
        return None
    day_str = m.group(1) or m.group(3)
    day = int(day_str) if day_str and 1 <= int(day_str) <= 31 else None
    return (month, day)


def extract_candidate_terms(text: str) -> list[str]:
    terms = set(_PROPER_NOUN_RE.findall(text)) | set(_ALNUM_ID_RE.findall(text)) | set(_DIGIT_ID_RE.findall(text))
    cleaned = [
        t for t in terms
        if t.strip().lower() not in _STOPWORD_PHRASES
        # A bare month name ("August") is a capitalized word too, but it's
        # never a genuine entity label in this domain (people/orgs/phones/
        # vehicles/locations) -- without this, a question like "what
        # happened around 14 August" spuriously "finds" an unrelated entity
        # via a narrative-text attribute merely mentioning that month (see
        # InvestigationRetriever.find_entities' attribute-fallback match),
        # which then blocks the real TEMPORAL-intent date lookup in
        # copilot.py. Caught by actually asking that exact question against
        # real data, not by inspection.
        and t.strip().lower() not in _MONTHS
    ]
    # Longest phrases first: "Suresh Yadav" should out-rank a stray "Suresh".
    return sorted(cleaned, key=len, reverse=True)


class InvestigationRetriever:
    def __init__(self, store: GraphStore, db: Session, investigation_id: str) -> None:
        self.store = store
        self.db = db
        self.investigation_id = investigation_id

    # -- entities -----------------------------------------------------
    def find_entities(self, text: str, limit: int = 6) -> list[Node]:
        """
        One entity per recognized term, not "every node search_nodes
        happens to match". GraphStore.search_nodes matches a term against a
        node's label AND its attribute values (right for general/universal
        search -- see app/services/investigation_search.py), but that's too
        loose here: a term naming one person can incidentally match an
        unrelated location/phone node whose attributes merely mention that
        name, which used to let PATH-intent questions ("show me the path
        between X and Y") silently path to the wrong second entity, and let
        a single term inflate a multi-hop `entities` list. Prefer an exact
        label match, then a label containing the term, before ever falling
        back to an attribute-only hit.
        """
        found: dict[str, Node] = {}
        for term in extract_candidate_terms(text):
            term_l = term.lower()
            candidates = self.store.search_nodes(term, limit=10)
            best = next((n for n in candidates if n.label.lower() == term_l), None)
            if best is None:
                best = next((n for n in candidates if term_l in n.label.lower()), None)
            if best is None and candidates:
                best = candidates[0]
            if best is not None:
                found.setdefault(best.id, best)
            if len(found) >= limit:
                break
        return list(found.values())[:limit]

    def get_entity(self, entity_id: str) -> Node | None:
        return self.store.get_node(entity_id)

    def neighborhood(self, entity_id: str, hops: int = 1):
        return self.store.neighbors(entity_id, hops=hops)

    # -- analytics ------------------------------------------------------
    def top_influencers(self, limit: int = 10) -> list[InfluencerScore]:
        return compute_influencers(self.store, top_n=limit)

    def influencer_rank(self, entity_id: str) -> InfluencerScore | None:
        for i in self.top_influencers(limit=50):
            if i.entity.id == entity_id:
                return i
        return None

    def signals(self, limit: int = 20) -> list[AnomalyFlag]:
        return run_all_detectors(self.store)[:limit]

    def signals_for_entities(self, entity_ids: set[str]) -> list[AnomalyFlag]:
        return [f for f in run_all_detectors(self.store) if entity_ids.intersection(f.entities_involved)]

    # -- paths ------------------------------------------------------------
    def path(self, source_id: str, target_id: str, max_hops: int = 6) -> PathResult:
        return find_path(self.store, source_id, target_id, max_hops=max_hops)

    # -- timeline -----------------------------------------------------------
    def timeline_for_entities(self, entity_ids: set[str], limit: int = 15) -> list[TimelineEventOut]:
        return timeline_for_entities(self.store, entity_ids, limit=limit)

    def timeline_near(self, month: int, day: int | None, limit: int = 10) -> list[TimelineEventOut]:
        """The investigation's own case timeline (calls/transactions/events
        -- `build_timeline`, unmodified), filtered to a mentioned month and
        ranked by proximity to a mentioned day if one was given. Deliberately
        NOT the audit-log "recent developments" feed RECENT-intent questions
        use -- that's app activity (logins, uploads), not case history."""
        same_month = [e for e in build_timeline(self.store, limit=500) if e.timestamp.month == month]
        if day is not None:
            same_month.sort(key=lambda e: abs(e.timestamp.day - day))
        else:
            same_month.sort(key=lambda e: e.timestamp, reverse=True)
        return same_month[:limit]

    # -- community structure --------------------------------------------
    def communities(self) -> list[Community]:
        return compute_communities(self.store)

    def bridge_entities(self, limit: int = 8) -> list[tuple[Node, int]]:
        """Entities whose direct neighbors span more than one detected
        community -- a real, derived "connects different parts of the
        network" signal, reusing the exact same `compute_communities`
        analytics every community-aware screen already shows (Overview's
        Analytical Intelligence panel, /api/analytics/communities), not a
        separate detector or an invented score."""
        comms = compute_communities(self.store)
        if len(comms) < 2:
            return []
        community_of: dict[str, int] = {}
        for c in comms:
            for m in c.members:
                community_of[m.id] = c.community_id

        results: list[tuple[Node, int]] = []
        for node_id, own_community in community_of.items():
            nodes, _edges = self.store.neighbors(node_id, hops=1)
            neighbor_communities = {community_of.get(n.id) for n in nodes if n.id != node_id}
            neighbor_communities.discard(None)
            neighbor_communities.discard(own_community)
            if not neighbor_communities:
                continue
            node = self.store.get_node(node_id)
            if node is not None:
                results.append((node, len(neighbor_communities) + 1))

        results.sort(key=lambda t: t[1], reverse=True)
        return results[:limit]

    # -- evidence -----------------------------------------------------------
    def evidence_by_refs(self, refs: set[str]) -> list[Evidence]:
        """`refs` are the raw evidence-id strings recorded on graph edges
        (`Edge.evidence`) -- for uploaded evidence these are
        f"evidence-{Evidence.id}" (see app/api/routes/evidence.py); anything
        else (e.g. a legacy /api/ingest/* document id with no Evidence row)
        is silently skipped rather than guessed at."""
        pks = {r[len("evidence-"):] for r in refs if r.startswith("evidence-")}
        if not pks:
            return []
        return (self.db.query(Evidence)
                .filter(Evidence.investigation_id == self.investigation_id, Evidence.id.in_(pks))
                .all())

    def evidence_for_entities(self, entity_ids: set[str]) -> list[Evidence]:
        refs: set[str] = set()
        for eid in entity_ids:
            _, edges = self.store.neighbors(eid, hops=1)
            for e in edges:
                if e.source in entity_ids or e.target in entity_ids:
                    refs.update(e.evidence)
        return self.evidence_by_refs(refs)
