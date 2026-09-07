from datetime import datetime, timedelta

from app.analytics.anomaly import detect_burst_and_short_calls, detect_circular_transactions
from app.analytics.centrality import compute_influencers
from app.analytics.community import compute_communities
from app.analytics.pathfinder import find_path
from app.db.graph_store import NetworkXGraphStore
from app.graph import schema
from app.graph.graph_builder import upsert_entity


def _star_graph(store):
    """Hub connected to 4 leaves -- hub should rank #1 by every centrality measure."""
    hub = upsert_entity(store, schema.PERSON, "Hub Person", "doc")
    for i in range(4):
        leaf = upsert_entity(store, schema.PERSON, f"Leaf {i}", "doc")
        store.upsert_edge(hub.id, leaf.id, schema.ASSOCIATED_WITH, weight=1.0, evidence="doc")
    return hub


def test_hub_node_ranks_first_by_influence():
    store = NetworkXGraphStore()
    hub = _star_graph(store)
    influencers = compute_influencers(store, top_n=5)
    assert influencers[0].entity.id == hub.id


def test_two_dense_clusters_detected_as_separate_communities():
    store = NetworkXGraphStore()
    a1, a2, a3 = (upsert_entity(store, schema.PERSON, f"A{i}", "doc") for i in range(3))
    b1, b2, b3 = (upsert_entity(store, schema.PERSON, f"B{i}", "doc") for i in range(3))
    for x, y in [(a1, a2), (a2, a3), (a1, a3)]:
        store.upsert_edge(x.id, y.id, schema.ASSOCIATED_WITH, weight=1.0, evidence="doc")
    for x, y in [(b1, b2), (b2, b3), (b1, b3)]:
        store.upsert_edge(x.id, y.id, schema.ASSOCIATED_WITH, weight=1.0, evidence="doc")
    # one weak bridge between the clusters
    store.upsert_edge(a1.id, b1.id, schema.ASSOCIATED_WITH, weight=0.1, evidence="doc")

    communities = compute_communities(store)
    assert len(communities) >= 2


def test_shortest_path_between_connected_entities():
    store = NetworkXGraphStore()
    a = upsert_entity(store, schema.PERSON, "A", "doc")
    b = upsert_entity(store, schema.PERSON, "B", "doc")
    c = upsert_entity(store, schema.PERSON, "C", "doc")
    store.upsert_edge(a.id, b.id, schema.ASSOCIATED_WITH, evidence="doc")
    store.upsert_edge(b.id, c.id, schema.ASSOCIATED_WITH, evidence="doc")

    result = find_path(store, a.id, c.id)
    assert result.found
    assert result.hops == 2


def test_burst_calling_detected():
    store = NetworkXGraphStore()
    a = upsert_entity(store, schema.PHONE, "9876543210", "doc")
    b = upsert_entity(store, schema.PHONE, "9812345670", "doc")
    base = datetime(2026, 8, 10, 9, 0, 0)
    for i in range(6):
        store.record_edge_event(
            a.id, b.id, schema.CALLED,
            event={"timestamp": (base + timedelta(hours=i)).isoformat(), "duration_seconds": 60},
            evidence="doc",
        )
    flags = detect_burst_and_short_calls(store)
    assert any(f.type == "BURST_CALLING" for f in flags)


def test_circular_transaction_detected():
    store = NetworkXGraphStore()
    a = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "ACC1", "doc")
    b = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "ACC2", "doc")
    c = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "ACC3", "doc")
    for src, dst in [(a, b), (b, c), (c, a)]:
        store.record_edge_event(src.id, dst.id, schema.TRANSACTED_WITH,
                                 event={"amount": 1000, "timestamp": "2026-08-05T10:00:00"}, evidence="doc")
    flags = detect_circular_transactions(store)
    assert any(f.type == "CIRCULAR_TRANSACTION" for f in flags)
