"""
Investigation Timeline and Financial Intelligence backend tests --
aggregation, chronological ordering, investigation isolation, and
transaction calculations, exercised through the real HTTP endpoints against
graph data built directly via the graph layer (deterministic, same
rationale as tests/test_integrity_and_resolution.py: not dependent on
spaCy's small-model NER tagging free text correctly).
"""
from __future__ import annotations

from tests.conftest import auth


def _make_investigation(client, token, name):
    return client.post("/api/investigations", json={"name": name}, headers=auth(token)).json()


def _seed_transaction_cycle(client, token, inv):
    """Three FINANCIAL_ACCOUNT nodes with a real circular flow -- same
    planted-pattern shape as the demo dataset, built directly so the test
    doesn't depend on CSV ingestion timing/parsing."""
    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    a = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "TESTACC1", "doc-a")
    b = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "TESTACC2", "doc-a")
    c = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "TESTACC3", "doc-a")
    store.record_edge_event(a.id, b.id, schema.TRANSACTED_WITH,
                             event={"amount": 1000.0, "timestamp": "2026-01-01T10:00:00"}, evidence="doc-a")
    store.record_edge_event(b.id, c.id, schema.TRANSACTED_WITH,
                             event={"amount": 900.0, "timestamp": "2026-01-02T10:00:00"}, evidence="doc-a")
    store.record_edge_event(c.id, a.id, schema.TRANSACTED_WITH,
                             event={"amount": 850.0, "timestamp": "2026-01-03T10:00:00"}, evidence="doc-a")
    return a, b, c


def _seed_call(client, token, inv):
    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    p1 = upsert_entity(store, schema.PHONE, "9000000001", "doc-b")
    p2 = upsert_entity(store, schema.PHONE, "9000000002", "doc-b")
    store.record_edge_event(p1.id, p2.id, schema.CALLED,
                             event={"timestamp": "2026-01-01T09:00:00", "duration_seconds": 60}, evidence="doc-b")
    return p1, p2


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_timeline_aggregates_real_events_chronologically(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Timeline Aggregation")
    _seed_transaction_cycle(client, investigator_token, inv)
    _seed_call(client, investigator_token, inv)

    res = client.get(f"/api/investigations/{inv['id']}/timeline", headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    # 3 transactions + 1 call + 1 CASE_EVENT (the investigation's own creation
    # is itself a real, audited timeline event -- see app/services/timeline.py's
    # _CASE_EVENT_ACTIONS).
    assert body["total_events"] == 5
    timestamps = [e["timestamp"] for e in body["events"]]
    assert timestamps == sorted(timestamps)  # ascending (default)
    kinds = {e["kind"] for e in body["events"]}
    assert kinds == {"TRANSACTION", "CALL", "CASE_EVENT"}


def test_timeline_descending_order(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Timeline Descending")
    _seed_transaction_cycle(client, investigator_token, inv)
    res = client.get(f"/api/investigations/{inv['id']}/timeline", params={"ascending": False},
                      headers=auth(investigator_token))
    timestamps = [e["timestamp"] for e in res.json()["events"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_timeline_filters_by_event_type_and_entity(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Timeline Filters")
    a, b, c = _seed_transaction_cycle(client, investigator_token, inv)
    _seed_call(client, investigator_token, inv)

    only_calls = client.get(f"/api/investigations/{inv['id']}/timeline", params={"event_type": "CALL"},
                             headers=auth(investigator_token)).json()
    assert only_calls["total_events"] == 1
    assert only_calls["events"][0]["kind"] == "CALL"

    only_a = client.get(f"/api/investigations/{inv['id']}/timeline", params={"entity_id": a.id},
                         headers=auth(investigator_token)).json()
    assert only_a["total_events"] == 2  # a->b and c->a


def test_timeline_never_leaks_across_investigations(client, investigator_token):
    inv_a = _make_investigation(client, investigator_token, "Timeline Isolation A")
    inv_b = _make_investigation(client, investigator_token, "Timeline Isolation B")
    _seed_transaction_cycle(client, investigator_token, inv_a)

    empty = client.get(f"/api/investigations/{inv_b['id']}/timeline", headers=auth(investigator_token)).json()
    assert empty["total_events"] == 1  # only inv_b's own CREATE_INVESTIGATION event -- none of inv_a's data
    assert empty["events"][0]["kind"] == "CASE_EVENT"

    populated = client.get(f"/api/investigations/{inv_a['id']}/timeline", headers=auth(investigator_token)).json()
    assert populated["total_events"] == 4  # 3 transactions + inv_a's own CREATE_INVESTIGATION event


def test_timeline_includes_evidence_registration_event(client, investigator_token):
    import io
    inv = _make_investigation(client, investigator_token, "Timeline Evidence")
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": f"TL-{inv['id'][:8]}", "title": "t"},
                        headers=auth(investigator_token)).json()
    client.post(f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
                headers=auth(investigator_token), data={"source_type": "FIR"},
                files={"file": ("timeline_ev.txt", io.BytesIO(b"some text"), "text/plain")})

    res = client.get(f"/api/investigations/{inv['id']}/timeline", headers=auth(investigator_token)).json()
    assert any(e["kind"] == "EVIDENCE_UPLOADED" for e in res["events"])


# ---------------------------------------------------------------------------
# Financial Intelligence
# ---------------------------------------------------------------------------

def test_financial_aggregation_computes_real_totals(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Financial Totals")
    a, b, c = _seed_transaction_cycle(client, investigator_token, inv)

    res = client.get(f"/api/investigations/{inv['id']}/financial", headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["transaction_count"] == 3
    assert body["total_outbound"] == 1000.0 + 900.0 + 850.0
    assert body["total_inbound"] == body["total_outbound"]  # closed system: every rupee lands somewhere in-set
    assert len(body["accounts"]) == 3

    acc1 = next(a2 for a2 in body["accounts"] if a2["account"]["label"] == "TESTACC1")
    assert acc1["total_outbound"] == 1000.0
    assert acc1["total_inbound"] == 850.0


def test_financial_detects_circular_flow(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Financial Circular")
    _seed_transaction_cycle(client, investigator_token, inv)
    res = client.get(f"/api/investigations/{inv['id']}/financial", headers=auth(investigator_token)).json()
    assert len(res["circular_flows"]) == 1
    assert res["circular_flows"][0]["evidence"] == ["doc-a"]


def test_financial_isolated_per_investigation(client, investigator_token):
    inv_a = _make_investigation(client, investigator_token, "Financial Isolation A")
    inv_b = _make_investigation(client, investigator_token, "Financial Isolation B")
    _seed_transaction_cycle(client, investigator_token, inv_a)

    empty = client.get(f"/api/investigations/{inv_b['id']}/financial", headers=auth(investigator_token)).json()
    assert empty["transaction_count"] == 0
    assert empty["accounts"] == []

    populated = client.get(f"/api/investigations/{inv_a['id']}/financial", headers=auth(investigator_token)).json()
    assert populated["transaction_count"] == 3


def test_financial_no_accounts_is_honest_empty_state(client, investigator_token):
    inv = _make_investigation(client, investigator_token, "Financial Empty")
    res = client.get(f"/api/investigations/{inv['id']}/financial", headers=auth(investigator_token)).json()
    assert res["accounts"] == []
    assert res["transaction_count"] == 0
    assert res["circular_flows"] == []
