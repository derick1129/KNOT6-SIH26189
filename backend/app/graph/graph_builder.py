"""
Turns extracted entities/relations (from NLP or a structured loader) into
graph nodes/edges. This is the only place that mints entity IDs, so ID
generation stays consistent no matter which source produced the entity.

ID strategy: a normalized natural key per type (e.g. a stripped phone
number, an upper-cased vehicle plate, a lower-cased person name) so the
*same* raw record from two different sources collapses onto the same
node automatically. Person names are the one type where this natural key
is unreliable ("Raj Malhotra" vs "Rajesh Malhotra" vs "R. Malhotra") --
that residual duplication is what app/resolution/entity_resolution.py
cleans up in a second pass using fuzzy matching, rather than trying to
solve it at ID-minting time.
"""
from __future__ import annotations

import hashlib
import re

from app.db.graph_store import Edge, GraphStore, Node
from app.graph import schema
from app.nlp.entity_extraction import ExtractionResult


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def make_entity_id(entity_type: str, text: str) -> str:
    key = _normalize(text).lower()
    if entity_type == schema.PHONE:
        key = re.sub(r"\D", "", key)[-10:]
    elif entity_type == schema.VEHICLE:
        key = re.sub(r"[\s\-]", "", key).upper()
    digest = hashlib.sha1(f"{entity_type}:{key}".encode()).hexdigest()[:12]
    return f"{entity_type.lower()}_{digest}"


def upsert_entity(store: GraphStore, entity_type: str, text: str, document_id: str | None = None,
                   attributes: dict | None = None) -> Node:
    node_id = make_entity_id(entity_type, text)
    return store.upsert_node(
        node_id=node_id, type=entity_type, label=_normalize(text),
        attributes=attributes or {}, source_document=document_id,
    )


def upsert_relation(store: GraphStore, source_id: str, target_id: str, relation_type: str,
                     document_id: str | None = None, weight: float = 1.0,
                     attributes: dict | None = None) -> Edge:
    return store.upsert_edge(
        source=source_id, target=target_id, type=relation_type,
        attributes=attributes or {}, weight=weight, evidence=document_id,
    )


def ingest_extraction(store: GraphStore, extraction: ExtractionResult, document_id: str,
                       source_type: str) -> tuple[int, int]:
    """Write an NLP ExtractionResult (from one document) into the graph. Returns (n_entities, n_relations)."""
    trust = schema.SOURCE_TRUST.get(source_type, 0.5)
    text_to_id: dict[tuple[str, str], str] = {}

    for ent in extraction.entities:
        node = upsert_entity(
            store, ent.type, ent.text, document_id=document_id,
            attributes={"last_seen_context": ent.sentence[:280]},
        )
        text_to_id[(ent.text.lower(), ent.type)] = node.id

    n_relations = 0
    for rel in extraction.relations:
        # relation entity type isn't tracked on ExtractedRelation directly;
        # resolve via the most recent entity dict built above by scanning types.
        source_id = next((v for (t, _typ), v in text_to_id.items() if t == rel.source_text.lower()), None)
        target_id = next((v for (t, _typ), v in text_to_id.items() if t == rel.target_text.lower()), None)
        if not source_id or not target_id or source_id == target_id:
            continue
        upsert_relation(
            store, source_id, target_id, rel.type, document_id=document_id,
            weight=round(rel.confidence * trust, 3),
            attributes={"sentence": rel.sentence[:280], "source_type": source_type},
        )
        n_relations += 1

    return len(extraction.entities), n_relations
