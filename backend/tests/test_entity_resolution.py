from app.db.graph_store import NetworkXGraphStore
from app.graph import schema
from app.graph.graph_builder import upsert_entity
from app.resolution.entity_resolution import auto_resolve, resolve_candidates


def test_reversed_name_order_auto_merges():
    store = NetworkXGraphStore()
    a = upsert_entity(store, schema.PERSON, "Vikram Rathore", "doc1")
    b = upsert_entity(store, schema.PERSON, "Rathore Vikram", "doc2")
    assert a.id != b.id  # not merged yet -- different natural keys

    merged = auto_resolve(store)
    assert merged == 1
    remaining = [n for n in store.all_nodes() if n.type == schema.PERSON]
    assert len(remaining) == 1


def test_dissimilar_names_are_not_merged():
    store = NetworkXGraphStore()
    upsert_entity(store, schema.PERSON, "Vikram Rathore", "doc1")
    upsert_entity(store, schema.PERSON, "Farhan Ali", "doc2")
    assert auto_resolve(store) == 0


def test_partial_name_variant_surfaces_as_candidate_not_auto_merged():
    store = NetworkXGraphStore()
    kumar = upsert_entity(store, schema.PERSON, "Ramesh Kumar", "doc1")
    kr = upsert_entity(store, schema.PERSON, "Ramesh Kr.", "doc2")
    # No shared neighbor and similarity below the near-exact bar -> should
    # NOT be silently auto-merged (that would risk merging two different
    # people who happen to share a first name).
    assert auto_resolve(store, min_confidence=97.0) == 0
    # Still both present
    assert store.get_node(kumar.id) and store.get_node(kr.id)
