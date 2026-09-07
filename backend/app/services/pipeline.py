"""
Orchestration layer: the one place that wires ingestion -> NLP ->
graph-building -> entity-resolution together, so API routes stay thin
and this sequence is unit-testable without HTTP.
"""
from __future__ import annotations

from app.db.graph_store import GraphStore
from app.graph.graph_builder import ingest_extraction, make_entity_id
from app.ingestion.loaders import load_cdr_records, load_criminal_history, load_financial_records
from app.models.schemas import BulkIngestSummary, EntityOut, IngestResult, RelationOut
from app.nlp.entity_extraction import extract_from_text
from app.resolution.entity_resolution import auto_resolve


def ingest_text_document(store: GraphStore, source_type: str, document_id: str, text: str,
                          metadata: dict | None = None) -> IngestResult:
    extraction = extract_from_text(text)
    metadata = metadata or {}

    # Stamp every relation from this document with its date, if known --
    # this is what enables the LOCATION_CONVERGENCE anomaly detector to
    # reason about co-presence in time.
    n_entities, n_relations = ingest_extraction(store, extraction, document_id, source_type)

    if metadata.get("document_date"):
        g = store.to_networkx()
        for u, v, k, d in g.edges(keys=True, data=True):
            if document_id in d.get("evidence", []) and "document_date" not in d.get("attributes", {}):
                d["attributes"]["document_date"] = metadata["document_date"]

    merged = auto_resolve(store)

    out_entities, out_relations = [], []
    seen_ids = set()
    for ent in extraction.entities:
        node_id = make_entity_id(ent.type, ent.text)
        node = store.get_node(node_id)
        if node and node.id not in seen_ids:
            seen_ids.add(node.id)
            out_entities.append(EntityOut(id=node.id, type=node.type, label=node.label,
                                           attributes=node.attributes, source_count=len(node.source_documents)))

    return IngestResult(
        document_id=document_id, entities_extracted=n_entities, relations_extracted=n_relations,
        entities=out_entities, relations=out_relations,
    )


def ingest_structured(store: GraphStore, source_type: str, records: list[dict],
                       document_id: str) -> BulkIngestSummary:
    loaders = {
        "cdr": load_cdr_records,
        "financial": load_financial_records,
        "criminal_history": load_criminal_history,
    }
    loader = loaders.get(source_type)
    if not loader:
        return BulkIngestSummary(documents_processed=0, records_processed=0, entities_created=0,
                                  entities_merged=0, relations_created=0,
                                  warnings=[f"Unknown structured source_type '{source_type}'."])

    n_entities, n_relations = loader(store, records, document_id)
    merged = auto_resolve(store)
    return BulkIngestSummary(
        documents_processed=1, records_processed=len(records), entities_created=n_entities,
        entities_merged=merged, relations_created=n_relations,
    )
