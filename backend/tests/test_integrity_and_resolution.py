"""
KNOT6 Phase 4 (Evidence Integrity + tamper-evident audit chain) and the
entity_resolution_decisions wiring -- both exercised through the real API,
against the real SQLite test database (see conftest.py), not mocked.
"""
from __future__ import annotations

import io

from tests.conftest import auth


def _make_investigation_and_case(client, token, name):
    inv = client.post("/api/investigations", json={"name": name}, headers=auth(token)).json()
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": f"T-{inv['id'][:8]}", "title": "Integrity test case"},
                        headers=auth(token)).json()
    return inv, case


def _upload(client, token, inv, case, text: bytes, filename="ev.txt", source_type="FIR"):
    res = client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(token), data={"source_type": source_type},
        files={"file": (filename, io.BytesIO(text), "text/plain")},
    )
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Evidence integrity
# ---------------------------------------------------------------------------

def test_evidence_upload_computes_sha256_hash(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Hash Test")
    ev = _upload(client, investigator_token, inv, case, b"Some FIR narrative text.")
    assert len(ev["sha256_hash"]) == 64
    int(ev["sha256_hash"], 16)  # valid hex


def test_verify_integrity_valid_for_untouched_file(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Verify Valid")
    ev = _upload(client, investigator_token, inv, case, b"Untouched evidence bytes.")

    meta = client.get(f"/api/evidence/{ev['id']}/integrity", headers=auth(investigator_token))
    assert meta.status_code == 200
    assert meta.json()["sha256_hash"] == ev["sha256_hash"]
    assert meta.json()["has_reference_hash"] is True

    result = client.post(f"/api/evidence/{ev['id']}/verify-integrity", headers=auth(investigator_token))
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "VALID"
    assert body["computed_hash"] == ev["sha256_hash"]


def test_verify_integrity_detects_tampered_file(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Verify Tamper")
    ev = _upload(client, investigator_token, inv, case, b"Original evidence bytes.")

    from app.db.postgres import SessionLocal
    from app.db.models import Evidence
    from app.services.storage import get_storage

    db = SessionLocal()
    row = db.get(Evidence, ev["id"])
    storage = get_storage()
    data = storage.read(row.storage_path)
    (storage.root / row.storage_path).write_bytes(data + b"TAMPERED")
    db.close()

    result = client.post(f"/api/evidence/{ev['id']}/verify-integrity", headers=auth(investigator_token))
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "INTEGRITY_VIOLATION"
    assert body["computed_hash"] != body["stored_hash"]


def test_verify_integrity_unavailable_when_no_reference_hash(client, investigator_token):
    """Evidence registered before hashing existed (sha256_hash="") must be
    reported honestly as UNAVAILABLE, never as a fabricated VALID/violation."""
    inv, case = _make_investigation_and_case(client, investigator_token, "No Hash")
    ev = _upload(client, investigator_token, inv, case, b"some bytes")

    from app.db.postgres import SessionLocal
    from app.db.models import Evidence

    db = SessionLocal()
    row = db.get(Evidence, ev["id"])
    row.sha256_hash = ""
    db.commit()
    db.close()

    result = client.post(f"/api/evidence/{ev['id']}/verify-integrity", headers=auth(investigator_token))
    assert result.json()["status"] == "UNAVAILABLE"


def test_evidence_integrity_requires_auth(client):
    res = client.get("/api/evidence/nonexistent/integrity")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Tamper-evident audit chain
# ---------------------------------------------------------------------------

def test_audit_chain_is_valid_after_normal_activity(client, investigator_token, admin_token):
    _make_investigation_and_case(client, investigator_token, "Chain Activity")
    result = client.get("/api/audit/verify", headers=auth(admin_token))
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "VALID"
    assert body["entries_checked"] > 0


def test_audit_chain_detects_tampered_row(client, investigator_token, admin_token):
    _make_investigation_and_case(client, investigator_token, "Chain Tamper")

    from app.db.postgres import SessionLocal
    from app.db.models import AuditEntryRow

    db = SessionLocal()
    row = db.query(AuditEntryRow).order_by(AuditEntryRow.seq.asc()).first()
    row_id, row_seq, original_actor = row.id, row.seq, row.actor
    row.actor = "someone-else"  # mutate content without recomputing the hash -- simulated tampering
    db.commit()
    db.close()

    result = client.get("/api/audit/verify", headers=auth(admin_token))
    body = result.json()
    assert body["status"] == "INTEGRITY_VIOLATION"
    assert body["first_broken_seq"] == row_seq

    # restore, so this test doesn't permanently poison the shared test-session chain for later tests
    db = SessionLocal()
    row2 = db.get(AuditEntryRow, row_id)
    row2.actor = original_actor
    db.commit()
    db.close()
    assert client.get("/api/audit/verify", headers=auth(admin_token)).json()["status"] == "VALID"


def test_audit_verify_requires_admin(client, investigator_token):
    res = client.get("/api/audit/verify", headers=auth(investigator_token))
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Entity resolution decisions, wired into the actual workflow
# ---------------------------------------------------------------------------

def _seed_near_duplicate_people(client, token, inv):
    """
    Build two near-duplicate PERSON nodes ("Ramesh Kumar" / "Ramesh K Kumar",
    92% token-sort-ratio -- above the configured 88% threshold) sharing one
    PHONE neighbor, directly through the graph layer rather than free-text
    NLP extraction: spaCy's small model (the documented, honest limitation
    in README.md/KNOT6_ARCHITECTURE.md) does not reliably tag this exact
    phrasing as two full PERSON entities, which would make this test flaky
    for a reason that has nothing to do with entity resolution itself. This
    mirrors tests/test_entity_resolution.py's own direct-graph approach.
    """
    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity, upsert_relation

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    a = upsert_entity(store, schema.PERSON, "Ramesh Kumar", "doc-a")
    b = upsert_entity(store, schema.PERSON, "Ramesh K Kumar", "doc-b")
    phone = upsert_entity(store, schema.PHONE, "9876543210", "doc-a")
    upsert_relation(store, a.id, phone.id, "OWNS", "doc-a")
    upsert_relation(store, b.id, phone.id, "OWNS", "doc-b")
    return a, b


def test_resolution_candidates_have_new_shape(client, investigator_token, analyst_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Resolution Shape")
    _seed_near_duplicate_people(client, investigator_token, inv)

    res = client.get("/api/entities/resolution/candidates",
                      params={"investigation_id": inv["id"]}, headers=auth(analyst_token))
    assert res.status_code == 200
    candidates = res.json()
    assert candidates, "expected at least one near-duplicate PERSON candidate"
    c = candidates[0]
    for field in ("keep_id", "merge_id", "confidence", "matching_reasons", "source_references", "decision_status"):
        assert field in c
    assert c["decision_status"] in ("AUTO_MERGE_ELIGIBLE", "REVIEW_REQUIRED")


def test_rejected_candidate_does_not_resurface(client, investigator_token, analyst_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Resolution Reject")
    _seed_near_duplicate_people(client, investigator_token, inv)

    candidates = client.get("/api/entities/resolution/candidates",
                             params={"investigation_id": inv["id"]}, headers=auth(analyst_token)).json()
    assert candidates
    c = candidates[0]

    decide = client.post(
        "/api/entities/resolution/decide", params={"investigation_id": inv["id"]},
        headers=auth(analyst_token),
        json={"keep_id": c["keep_id"], "merge_id": c["merge_id"], "decision": "REJECTED", "reason": "distinct people"},
    )
    assert decide.status_code == 200, decide.text
    assert decide.json()["decision"] == "REJECTED"

    again = client.get("/api/entities/resolution/candidates",
                        params={"investigation_id": inv["id"]}, headers=auth(analyst_token)).json()
    assert not any(x["keep_id"] == c["keep_id"] and x["merge_id"] == c["merge_id"] for x in again)

    decisions = client.get("/api/entities/resolution/decisions",
                            params={"investigation_id": inv["id"]}, headers=auth(analyst_token)).json()
    assert any(d["decision"] == "REJECTED" for d in decisions)


def test_approved_candidate_merges_and_stops_appearing(client, investigator_token, analyst_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Resolution Approve")
    _seed_near_duplicate_people(client, investigator_token, inv)

    candidates = client.get("/api/entities/resolution/candidates",
                             params={"investigation_id": inv["id"]}, headers=auth(analyst_token)).json()
    assert candidates
    c = candidates[0]

    decide = client.post(
        "/api/entities/resolution/decide", params={"investigation_id": inv["id"]},
        headers=auth(analyst_token),
        json={"keep_id": c["keep_id"], "merge_id": c["merge_id"], "decision": "APPROVED", "reason": "same person"},
    )
    assert decide.status_code == 200, decide.text

    graph = client.get("/api/graph", params={"investigation_id": inv["id"]}, headers=auth(investigator_token)).json()
    node_ids = {n["id"] for n in graph["nodes"]}
    assert c["merge_id"] not in node_ids
    assert c["keep_id"] in node_ids


def test_resolution_decide_requires_analyst_or_admin(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Resolution RBAC")
    res = client.post(
        "/api/entities/resolution/decide", params={"investigation_id": inv["id"]},
        headers=auth(investigator_token),
        json={"keep_id": "x", "merge_id": "y", "decision": "REJECTED"},
    )
    assert res.status_code == 403
