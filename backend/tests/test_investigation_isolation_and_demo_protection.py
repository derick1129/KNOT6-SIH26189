"""
Regression tests for the KNOT6 Operation Nexus incident:

  1. A real "Add Intelligence" upload directly polluted the bundled demo
     investigation ("Operation Nexus") because nothing distinguished it from
     any other investigation -- ingestion is (correctly) additive into
     whichever investigation/case is selected. `Investigation.is_demo_seed`
     + `ensure_not_demo_protected` (app/services/evidence_processing.py) is
     the fix: every ingestion entry point now refuses to write into a
     demo-flagged investigation.

  2. The graph itself lives only in-process memory (see
     app/db/graph_store.py's module docstring); a restart silently loses any
     real investigation's extracted graph even though its Evidence rows
     persist in PostgreSQL/SQLite right next to it.
     `app/services/graph_recovery.py::rebuild_missing_investigation_graphs`
     is the fix.

  3. `app/services/graph_recovery.py::reseed_demo_investigation` (exposed as
     `POST /investigations/{id}/reseed-demo`) is how Operation Nexus itself
     gets restored to its one canonical source (backend/data/demo/ via
     app/services/seed_demo.py) rather than by hand.

`test_two_investigations_never_see_each_others_graph_data` in
test_phase1_investigations.py already proves the underlying isolation
primitive (ScopedGraphStore) holds; these tests are specifically about the
demo-protection guard and the two recovery paths built on top of it.
"""
from __future__ import annotations

import io

from tests.conftest import auth


def _get_demo_investigation(client, token) -> dict:
    invs = client.get("/api/investigations", headers=auth(token)).json()
    demo = next(i for i in invs if i["name"] == "Operation Nexus")
    assert demo["is_demo_seed"] is True
    return demo


def _demo_case(client, token, demo_investigation_id: str) -> dict:
    cases = client.get(f"/api/investigations/{demo_investigation_id}/cases", headers=auth(token)).json()
    return next(c for c in cases if c["case_number"] == "CASE-001")


def _graph_counts(client, token, investigation_id: str) -> tuple[int, int]:
    graph = client.get("/api/graph", params={"investigation_id": investigation_id}, headers=auth(token)).json()
    return len(graph["nodes"]), len(graph["edges"])


def _make_investigation_and_case(client, token, name: str) -> tuple[dict, dict]:
    inv = client.post("/api/investigations", json={"name": name}, headers=auth(token)).json()
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": f"T-{inv['id'][:8]}", "title": "Evidence case"},
                        headers=auth(token)).json()
    return inv, case


# ---------------------------------------------------------------------------
# 1. The demo dataset is flagged, and matches its documented canonical size
# ---------------------------------------------------------------------------

def test_demo_investigation_is_flagged_and_matches_documented_baseline(client, investigator_token):
    demo = _get_demo_investigation(client, investigator_token)
    nodes, edges = _graph_counts(client, investigator_token, demo["id"])
    # See docs/DEMO_DATA.md -- the canonical seed_demo.py output.
    assert nodes == 59
    assert edges == 102
    graph = client.get("/api/graph", params={"investigation_id": demo["id"]}, headers=auth(investigator_token)).json()
    persons = [n for n in graph["nodes"] if n["type"] == "PERSON"]
    assert len(persons) == 17


# ---------------------------------------------------------------------------
# 2. Add Intelligence can no longer land in the demo investigation
# ---------------------------------------------------------------------------

def test_evidence_upload_into_demo_investigation_is_rejected_and_leaves_it_unchanged(client, investigator_token):
    demo = _get_demo_investigation(client, investigator_token)
    case = _demo_case(client, investigator_token, demo["id"])
    before = _graph_counts(client, investigator_token, demo["id"])

    res = client.post(
        f"/api/investigations/{demo['id']}/cases/{case['id']}/evidence",
        headers=auth(investigator_token),
        data={"source_type": "INTELLIGENCE_REPORT"},
        files={"file": ("nightfall.txt", io.BytesIO(b"A new courier network was observed in Nagpur."), "text/plain")},
    )
    assert res.status_code == 409
    assert "protected demo dataset" in res.json()["detail"]

    after = _graph_counts(client, investigator_token, demo["id"])
    assert after == before


def test_legacy_ingest_text_into_demo_investigation_is_rejected(client, investigator_token):
    demo = _get_demo_investigation(client, investigator_token)
    before = _graph_counts(client, investigator_token, demo["id"])

    res = client.post(
        "/api/ingest/text",
        headers=auth(investigator_token),
        json={
            "source_type": "intel_report", "document_id": "nightfall-legacy",
            "text": "A new courier network was observed in Nagpur.",
            "metadata": {}, "investigation_id": demo["id"],
        },
    )
    assert res.status_code == 409

    after = _graph_counts(client, investigator_token, demo["id"])
    assert after == before


def test_legacy_ingest_csv_into_demo_investigation_is_rejected(client, investigator_token):
    demo = _get_demo_investigation(client, investigator_token)
    before = _graph_counts(client, investigator_token, demo["id"])

    csv_bytes = b"caller,callee,duration\n9990001111,9990002222,45\n"
    res = client.post(
        "/api/ingest/csv/cdr",
        params={"investigation_id": demo["id"]},
        headers=auth(investigator_token),
        files={"file": ("extra.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert res.status_code == 409

    after = _graph_counts(client, investigator_token, demo["id"])
    assert after == before


def test_real_investigation_uploads_are_unaffected_by_the_demo_guard(client, investigator_token):
    """The guard is specific to `is_demo_seed` investigations -- every
    ordinary investigation keeps accepting uploads exactly as before."""
    inv, case = _make_investigation_and_case(client, investigator_token, "Not The Demo")
    res = client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(investigator_token), data={"source_type": "FIR"},
        files={"file": ("f.txt", io.BytesIO(b"Deepak Nair met Suresh Rao in Kochi."), "text/plain")},
    )
    assert res.status_code == 200
    assert res.json()["processing_status"] == "PROCESSED"


# ---------------------------------------------------------------------------
# 3. Uploading into one investigation can never mutate another's graph
# ---------------------------------------------------------------------------

def test_add_intelligence_to_one_investigation_never_changes_another(client, investigator_token):
    inv_a, case_a = _make_investigation_and_case(client, investigator_token, "Nexus Stand-in A")
    inv_b, case_b = _make_investigation_and_case(client, investigator_token, "Nightfall Stand-in B")

    nodes_a0, edges_a0 = _graph_counts(client, investigator_token, inv_a["id"])
    nodes_b0, edges_b0 = _graph_counts(client, investigator_token, inv_b["id"])
    demo = _get_demo_investigation(client, investigator_token)
    demo_before = _graph_counts(client, investigator_token, demo["id"])

    res = client.post(
        f"/api/investigations/{inv_a['id']}/cases/{case_a['id']}/evidence",
        headers=auth(investigator_token), data={"source_type": "INTELLIGENCE_REPORT"},
        files={"file": ("nightfall.txt", io.BytesIO(
            b"Manoj Bhatt coordinated with Farhan Ali and Priya Deshmukh across three warehouses in Nagpur."
        ), "text/plain")},
    )
    assert res.status_code == 200
    assert res.json()["processing_summary"]["entities_extracted"] > 0

    nodes_a1, edges_a1 = _graph_counts(client, investigator_token, inv_a["id"])
    nodes_b1, edges_b1 = _graph_counts(client, investigator_token, inv_b["id"])
    demo_after = _graph_counts(client, investigator_token, demo["id"])

    assert nodes_a1 > nodes_a0  # the target investigation actually grew
    assert (nodes_b1, edges_b1) == (nodes_b0, edges_b0)  # sibling investigation: zero change
    assert demo_after == demo_before  # demo investigation: zero change


# ---------------------------------------------------------------------------
# 4. Restoring the demo dataset from its canonical source
# ---------------------------------------------------------------------------

def test_reseed_demo_restores_canonical_counts_and_purges_stray_evidence(client, investigator_token, admin_token):
    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.db.models import Evidence
    from app.db.postgres import SessionLocal
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity

    demo = _get_demo_investigation(client, investigator_token)
    case = _demo_case(client, investigator_token, demo["id"])
    baseline = _graph_counts(client, investigator_token, demo["id"])

    # Simulate the pre-fix incident: a real entity landing in the demo
    # graph, plus the Evidence row that (pre-fix) would have accompanied
    # it -- done directly at the graph/DB layer, bypassing the now-fixed
    # HTTP path, exactly as the original bug did before this fix existed.
    store = ScopedGraphStore(get_graph_store(), demo["id"])
    upsert_entity(store, schema.PERSON, "Intruder Entity", "stray-doc")
    assert _graph_counts(client, investigator_token, demo["id"]) != baseline

    db = SessionLocal()
    try:
        stray = Evidence(
            investigation_id=demo["id"], case_id=case["id"], filename="stray.txt",
            original_filename="stray.txt", source_type="INTELLIGENCE_REPORT", mime_type="text/plain",
            file_size=10, storage_path="stray.txt", uploaded_by="investigator",
            processing_status="PROCESSED", sha256_hash="0" * 64,
        )
        db.add(stray)
        db.commit()
        stray_id = stray.id
    finally:
        db.close()

    evidence_before = client.get(f"/api/investigations/{demo['id']}/evidence", headers=auth(admin_token)).json()
    assert any(e["id"] == stray_id for e in evidence_before)

    # Non-admin cannot trigger the restore.
    forbidden = client.post(f"/api/investigations/{demo['id']}/reseed-demo", headers=auth(investigator_token))
    assert forbidden.status_code == 403

    # A non-demo investigation refuses outright -- there is no canonical
    # source to restore a real investigation from.
    real_inv, _ = _make_investigation_and_case(client, investigator_token, "Reseed Refusal Target")
    refused = client.post(f"/api/investigations/{real_inv['id']}/reseed-demo", headers=auth(admin_token))
    assert refused.status_code == 400

    restored = client.post(f"/api/investigations/{demo['id']}/reseed-demo", headers=auth(admin_token))
    assert restored.status_code == 200
    body = restored.json()
    assert body["removed_evidence_ids"] == [stray_id]

    assert _graph_counts(client, investigator_token, demo["id"]) == baseline
    graph = client.get("/api/graph", params={"investigation_id": demo["id"]}, headers=auth(investigator_token)).json()
    assert all(n["label"] != "Intruder Entity" for n in graph["nodes"])

    evidence_after = client.get(f"/api/investigations/{demo['id']}/evidence", headers=auth(admin_token)).json()
    assert evidence_after == []


# ---------------------------------------------------------------------------
# 5. Graph durability: a real investigation's graph survives an in-memory reset
# ---------------------------------------------------------------------------

def test_startup_rebuild_restores_a_real_investigations_graph_but_never_touches_the_demo_one(
    client, investigator_token,
):
    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.db.postgres import SessionLocal
    from app.services.graph_recovery import rebuild_missing_investigation_graphs

    inv, case = _make_investigation_and_case(client, investigator_token, "Durability Test")
    res = client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(investigator_token), data={"source_type": "FIR"},
        files={"file": ("f.txt", io.BytesIO(b"Anita Bose called Rajeev Menon in Bhopal."), "text/plain")},
    )
    assert res.status_code == 200
    nodes_before, edges_before = _graph_counts(client, investigator_token, inv["id"])
    assert nodes_before > 0

    demo = _get_demo_investigation(client, investigator_token)
    demo_before = _graph_counts(client, investigator_token, demo["id"])

    # Simulate "the process restarted and the in-memory graph came back
    # empty" for this one investigation only -- not a global store.clear(),
    # which would also (harmlessly, but noisily) wipe every other test's
    # investigation and the demo dataset sharing the same process-wide
    # NetworkX instance.
    ScopedGraphStore(get_graph_store(), inv["id"]).clear()
    assert _graph_counts(client, investigator_token, inv["id"]) == (0, 0)

    db = SessionLocal()
    try:
        rebuilt = rebuild_missing_investigation_graphs(db)
    finally:
        db.close()

    assert inv["id"] in rebuilt
    assert _graph_counts(client, investigator_token, inv["id"]) == (nodes_before, edges_before)
    # The demo investigation is deliberately out of scope for this rebuild
    # path (it has its own canonical-source restore, and should have no
    # Evidence rows to replay in the first place now that uploads to it are
    # refused) -- confirm it was left alone.
    assert demo["id"] not in rebuilt
    assert _graph_counts(client, investigator_token, demo["id"]) == demo_before
