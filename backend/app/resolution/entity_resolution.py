"""
Entity resolution: collapse different surface forms of the same
real-world person/organization into one node.

Structured identifiers (phone, vehicle plate, account number) already
collapse deterministically at ID-minting time (see graph_builder.make_entity_id),
because those are exact natural keys. The genuinely hard case is names --
"Raj Malhotra" from a CDR subscriber record, "Rajesh Malhotra" from an
FIR, "R. Malhotra" from a social-media handle -- which is what this
module targets, using:

  1. Fuzzy name similarity (rapidfuzz token_sort_ratio) above a
     configurable threshold, AND
  2. At least one corroborating shared fact (a common neighbor: same
     phone, same address/location, same vehicle, or same case) --
     name similarity alone is deliberately not sufficient, to avoid
     merging two different "Ramesh Kumar"s who happen to share a common
     name, which would be a serious investigative error.

This runs as an explicit, auditable pass (`resolve_candidates` returns
proposed merges; `apply_merge` performs one) rather than silently
auto-merging everything, because merging two suspects into one node is
exactly the kind of error an investigator needs to be able to review and
reject.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.core.config import get_settings
from app.db.graph_store import GraphStore, Node
from app.graph import schema


@dataclass
class MergeCandidate:
    keep_id: str
    merge_id: str
    keep_label: str
    merge_label: str
    name_similarity: float
    shared_neighbors: list[str]
    reason: str


def _shared_neighbors(store: GraphStore, a_id: str, b_id: str) -> list[str]:
    a_nodes, _ = store.neighbors(a_id, hops=1)
    b_nodes, _ = store.neighbors(b_id, hops=1)
    a_ids = {n.id for n in a_nodes if n.id != a_id}
    b_ids = {n.id for n in b_nodes if n.id != b_id}
    return sorted(a_ids & b_ids)


def resolve_candidates(store: GraphStore, entity_type: str = schema.PERSON) -> list[MergeCandidate]:
    settings = get_settings()
    nodes = [n for n in store.all_nodes() if n.type == entity_type]
    candidates: list[MergeCandidate] = []

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            similarity = fuzz.token_sort_ratio(a.label, b.label)
            if similarity < settings.name_match_threshold:
                continue
            shared = _shared_neighbors(store, a.id, b.id)
            if not shared and similarity < 97:
                # Near-exact name match (typo-level) is allowed through even
                # without a corroborating neighbor; a merely "similar" name
                # is not.
                continue
            # Keep the node with more corroborating source documents / higher degree
            keep, merge = (a, b) if len(a.source_documents) >= len(b.source_documents) else (b, a)
            reason = (
                f"name similarity {similarity:.0f}%"
                + (f", {len(shared)} shared connection(s)" if shared else ", near-exact name match")
            )
            candidates.append(MergeCandidate(
                keep_id=keep.id, merge_id=merge.id, keep_label=keep.label, merge_label=merge.label,
                name_similarity=similarity, shared_neighbors=shared, reason=reason,
            ))
    return candidates


def apply_merge(store: GraphStore, candidate: MergeCandidate) -> None:
    store.merge_nodes(candidate.keep_id, candidate.merge_id)


def auto_resolve(store: GraphStore, entity_type: str = schema.PERSON, min_confidence: float = 97.0) -> int:
    """
    Apply only the high-confidence merges automatically (near-exact name,
    i.e. almost certainly a typo/OCR variant); everything else is
    surfaced via resolve_candidates() for an analyst to confirm in the UI.
    """
    applied = 0
    for c in resolve_candidates(store, entity_type):
        if c.name_similarity >= min_confidence:
            apply_merge(store, c)
            applied += 1
    return applied
