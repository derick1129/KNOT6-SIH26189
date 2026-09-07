"""
Structured-data loaders: one function per source type named in the PS
(Call Detail Records, financial transaction records, criminal-history
databases, social-media intelligence). Unstructured sources (FIRs,
surveillance reports, intelligence summaries) go through
app/nlp/entity_extraction.py instead -- see services/pipeline.py, which
is where both paths converge on the same graph.

Every loader accepts an in-memory list of dicts (already parsed from
CSV/JSON by the API layer) rather than a file path, so the same function
serves a file upload, a paste-in-the-browser CSV, and a unit test
fixture identically.
"""
from __future__ import annotations

from app.db.graph_store import GraphStore
from app.graph import schema
from app.graph.graph_builder import upsert_entity


def load_cdr_records(store: GraphStore, records: list[dict], document_id: str) -> tuple[int, int]:
    """
    Expected columns: caller, callee, timestamp (ISO-ish), duration_seconds,
    [caller_name], [callee_name], [tower_location].
    """
    n_entities, n_relations = 0, 0
    for row in records:
        caller, callee = str(row.get("caller", "")).strip(), str(row.get("callee", "")).strip()
        if not caller or not callee:
            continue
        caller_node = upsert_entity(store, schema.PHONE, caller, document_id,
                                     {"subscriber_name": row.get("caller_name", "")})
        callee_node = upsert_entity(store, schema.PHONE, callee, document_id,
                                     {"subscriber_name": row.get("callee_name", "")})
        n_entities += 2

        # If subscriber names are known, also create/link a PERSON node --
        # this is what lets a phone-based CDR graph merge with a
        # name-based FIR graph during entity resolution.
        for phone_node, name_key in ((caller_node, "caller_name"), (callee_node, "callee_name")):
            name = row.get(name_key)
            if name:
                person_node = upsert_entity(store, schema.PERSON, str(name), document_id)
                store.upsert_edge(person_node.id, phone_node.id, schema.OWNS, weight=1.0, evidence=document_id)

        store.record_edge_event(
            caller_node.id, callee_node.id, schema.CALLED,
            event={
                "timestamp": row.get("timestamp"),
                "duration_seconds": _to_int(row.get("duration_seconds")),
                "tower_location": row.get("tower_location"),
            },
            evidence=document_id,
        )
        n_relations += 1

        if row.get("tower_location"):
            loc_node = upsert_entity(store, schema.LOCATION, str(row["tower_location"]), document_id)
            store.upsert_edge(caller_node.id, loc_node.id, schema.PRESENT_AT, weight=0.5, evidence=document_id,
                               attributes={"document_date": row.get("timestamp")})
            n_relations += 1

    return n_entities, n_relations


def load_financial_records(store: GraphStore, records: list[dict], document_id: str) -> tuple[int, int]:
    """Expected columns: from_account, to_account, amount, timestamp, [mode], [from_name], [to_name]."""
    n_entities, n_relations = 0, 0
    for row in records:
        src, dst = str(row.get("from_account", "")).strip(), str(row.get("to_account", "")).strip()
        if not src or not dst:
            continue
        src_node = upsert_entity(store, schema.FINANCIAL_ACCOUNT, src, document_id,
                                  {"holder_name": row.get("from_name", "")})
        dst_node = upsert_entity(store, schema.FINANCIAL_ACCOUNT, dst, document_id,
                                  {"holder_name": row.get("to_name", "")})
        n_entities += 2

        for acct_node, name_key in ((src_node, "from_name"), (dst_node, "to_name")):
            name = row.get(name_key)
            if name:
                person_node = upsert_entity(store, schema.PERSON, str(name), document_id)
                store.upsert_edge(person_node.id, acct_node.id, schema.OWNS, weight=1.0, evidence=document_id)

        store.record_edge_event(
            src_node.id, dst_node.id, schema.TRANSACTED_WITH,
            event={"amount": _to_float(row.get("amount")), "timestamp": row.get("timestamp"),
                   "mode": row.get("mode")},
            evidence=document_id,
        )
        n_relations += 1
    return n_entities, n_relations


def load_criminal_history(store: GraphStore, records: list[dict], document_id: str) -> tuple[int, int]:
    """Expected columns: name, [phone], [vehicle], [aliases], [prior_cases], [address]."""
    n_entities, n_relations = 0, 0
    for row in records:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        person = upsert_entity(store, schema.PERSON, name, document_id, {
            "aliases": row.get("aliases", ""),
            "prior_cases": row.get("prior_cases", ""),
            "address": row.get("address", ""),
            "risk_flag": "known_offender",
        })
        n_entities += 1
        if row.get("phone"):
            phone = upsert_entity(store, schema.PHONE, str(row["phone"]), document_id)
            store.upsert_edge(person.id, phone.id, schema.OWNS, weight=1.0, evidence=document_id)
            n_relations += 1
        if row.get("vehicle"):
            vehicle = upsert_entity(store, schema.VEHICLE, str(row["vehicle"]), document_id)
            store.upsert_edge(person.id, vehicle.id, schema.OWNS, weight=1.0, evidence=document_id)
            n_relations += 1
        if row.get("address"):
            loc = upsert_entity(store, schema.LOCATION, str(row["address"]), document_id)
            store.upsert_edge(person.id, loc.id, schema.PRESENT_AT, weight=1.0, evidence=document_id)
            n_relations += 1
    return n_entities, n_relations


def _to_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
