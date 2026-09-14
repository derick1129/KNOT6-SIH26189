"""
KNOT6 Phase 1 tests: PostgreSQL-backed persistence (users, investigations,
cases, evidence), investigation-scoped graph isolation, RBAC, and a
confirmation that the pre-Phase-1 intelligence engine (ingestion, entity
resolution, graph analytics) is completely unaffected when exercised
through the new investigation-scoped path.

Uses the FastAPI TestClient against the real app + a throwaway SQLite DB
(see conftest.py) -- unlike the pre-Phase-1 tests, these necessarily go
through the HTTP layer because investigation/case/evidence and RBAC are
API-level concerns, not pure-function concerns.
"""
from __future__ import annotations

import io

from tests.conftest import auth


# ---------------------------------------------------------------------------
# Users / auth persistence
# ---------------------------------------------------------------------------

def test_all_four_demo_roles_persist_and_can_log_in(client):
    for username, password in [
        ("admin", "admin123"), ("investigator", "investigator123"),
        ("analyst", "analyst123"), ("viewer", "viewer123"),
    ]:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, f"{username} login failed: {res.text}"
        assert res.json()["role"] == username if username != "admin" else True


def test_wrong_password_rejected(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

def test_create_and_read_investigation(client, investigator_token):
    res = client.post("/api/investigations", json={"name": "Test Investigation A", "description": "unit test"},
                       headers=auth(investigator_token))
    assert res.status_code == 200, res.text
    inv = res.json()
    assert inv["status"] == "ACTIVE"
    assert inv["case_count"] == 0

    got = client.get(f"/api/investigations/{inv['id']}", headers=auth(investigator_token))
    assert got.status_code == 200
    assert got.json()["name"] == "Test Investigation A"


def test_investigation_create_requires_write_role(client, viewer_token):
    res = client.post("/api/investigations", json={"name": "Should Fail"}, headers=auth(viewer_token))
    assert res.status_code == 403


def test_investigation_read_allowed_for_viewer(client, viewer_token):
    res = client.get("/api/investigations", headers=auth(viewer_token))
    assert res.status_code == 200


def test_unauthenticated_request_rejected(client):
    res = client.get("/api/investigations")
    assert res.status_code == 401


def test_investigation_not_found(client, investigator_token):
    res = client.get("/api/investigations/does-not-exist", headers=auth(investigator_token))
    assert res.status_code == 404


def test_archive_investigation(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "To Archive"}, headers=auth(investigator_token)).json()
    res = client.post(f"/api/investigations/{inv['id']}/archive", headers=auth(investigator_token))
    assert res.status_code == 200
    assert res.json()["status"] == "ARCHIVED"


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_create_case_under_investigation(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Case Parent"}, headers=auth(investigator_token)).json()
    res = client.post(f"/api/investigations/{inv['id']}/cases",
                       json={"case_number": "T-CASE-001", "title": "A test case"},
                       headers=auth(investigator_token))
    assert res.status_code == 200, res.text
    case = res.json()
    assert case["investigation_id"] == inv["id"]
    assert case["status"] == "OPEN"
    assert case["priority"] == "MEDIUM"


def test_duplicate_case_number_rejected(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Dup Test"}, headers=auth(investigator_token)).json()
    body = {"case_number": "T-CASE-DUP", "title": "First"}
    first = client.post(f"/api/investigations/{inv['id']}/cases", json=body, headers=auth(investigator_token))
    assert first.status_code == 200
    second = client.post(f"/api/investigations/{inv['id']}/cases", json=body, headers=auth(investigator_token))
    assert second.status_code == 409


def test_case_scoped_to_its_own_investigation(client, investigator_token):
    inv_a = client.post("/api/investigations", json={"name": "Inv A"}, headers=auth(investigator_token)).json()
    inv_b = client.post("/api/investigations", json={"name": "Inv B"}, headers=auth(investigator_token)).json()
    case = client.post(f"/api/investigations/{inv_a['id']}/cases",
                        json={"case_number": "T-CASE-SCOPE", "title": "Scoped"},
                        headers=auth(investigator_token)).json()
    # Fetching case A through investigation B's URL must 404, not leak.
    leaked = client.get(f"/api/investigations/{inv_b['id']}/cases/{case['id']}", headers=auth(investigator_token))
    assert leaked.status_code == 404
    ok = client.get(f"/api/investigations/{inv_a['id']}/cases/{case['id']}", headers=auth(investigator_token))
    assert ok.status_code == 200


def test_close_case(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Close Test"}, headers=auth(investigator_token)).json()
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": "T-CASE-CLOSE", "title": "Closeable"},
                        headers=auth(investigator_token)).json()
    res = client.post(f"/api/investigations/{inv['id']}/cases/{case['id']}/close", headers=auth(investigator_token))
    assert res.status_code == 200
    assert res.json()["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# Evidence registration + the existing ingestion pipeline, unmodified
# ---------------------------------------------------------------------------

def _make_investigation_and_case(client, token, name="Evidence Test"):
    inv = client.post("/api/investigations", json={"name": name}, headers=auth(token)).json()
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": f"T-{inv['id'][:8]}", "title": "Evidence case"},
                        headers=auth(token)).json()
    return inv, case


def test_evidence_upload_runs_existing_pipeline_and_persists_metadata(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token)
    text = b"Rahul Kumar called Imran Sheikh near Central Market."
    res = client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(investigator_token),
        data={"source_type": "FIR", "description": "unit test FIR"},
        files={"file": ("test_fir.txt", io.BytesIO(text), "text/plain")},
    )
    assert res.status_code == 200, res.text
    ev = res.json()
    assert ev["processing_status"] == "PROCESSED"
    assert ev["processing_summary"]["entities_extracted"] >= 2  # Rahul Kumar, Imran Sheikh (at least)

    listed = client.get(f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
                         headers=auth(investigator_token))
    assert listed.status_code == 200
    assert any(e["id"] == ev["id"] for e in listed.json())

    status = client.get(f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence/{ev['id']}/status",
                         headers=auth(investigator_token))
    assert status.status_code == 200
    assert status.json()["processing_status"] == "PROCESSED"


def test_evidence_extracted_entities_land_in_the_investigations_graph(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token)
    text = b"Rohan Verma transferred money to Neha Kapoor in Pune."
    client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(investigator_token),
        data={"source_type": "FIR"},
        files={"file": ("test_fir2.txt", io.BytesIO(text), "text/plain")},
    )
    graph = client.get("/api/graph", params={"investigation_id": inv["id"]}, headers=auth(investigator_token))
    assert graph.status_code == 200
    labels = {n["label"] for n in graph.json()["nodes"]}
    assert "Rohan Verma" in labels
    assert "Neha Kapoor" in labels
    # And node ids must be the plain, unprefixed form -- not the physical
    # "inv_<id>::..." storage key -- confirming ScopedGraphStore unscopes
    # correctly at the API boundary.
    assert all("::" not in n["id"] for n in graph.json()["nodes"])


def test_evidence_upload_requires_write_role(client, viewer_token, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, name="Viewer Cannot Upload")
    res = client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(viewer_token),
        data={"source_type": "FIR"},
        files={"file": ("x.txt", io.BytesIO(b"text"), "text/plain")},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Investigation isolation (the core Phase 1 requirement)
# ---------------------------------------------------------------------------

def test_two_investigations_never_see_each_others_graph_data(client, investigator_token):
    inv_a, case_a = _make_investigation_and_case(client, investigator_token, name="Isolation A")
    inv_b, case_b = _make_investigation_and_case(client, investigator_token, name="Isolation B")

    client.post(f"/api/investigations/{inv_a['id']}/cases/{case_a['id']}/evidence",
                headers=auth(investigator_token), data={"source_type": "FIR"},
                files={"file": ("a.txt", io.BytesIO(b"Arjun Singh met Nisha Rao in Pune."), "text/plain")})
    client.post(f"/api/investigations/{inv_b['id']}/cases/{case_b['id']}/evidence",
                headers=auth(investigator_token), data={"source_type": "FIR"},
                files={"file": ("b.txt", io.BytesIO(b"Karan Patel called Sunita Joshi in Surat."), "text/plain")})

    graph_a = client.get("/api/graph", params={"investigation_id": inv_a["id"]}, headers=auth(investigator_token)).json()
    graph_b = client.get("/api/graph", params={"investigation_id": inv_b["id"]}, headers=auth(investigator_token)).json()

    labels_a = {n["label"] for n in graph_a["nodes"]}
    labels_b = {n["label"] for n in graph_b["nodes"]}

    assert "Arjun Singh" in labels_a and "Karan Patel" not in labels_a
    assert "Karan Patel" in labels_b and "Arjun Singh" not in labels_b


def test_brand_new_investigation_has_an_empty_graph(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Fresh And Empty"}, headers=auth(investigator_token)).json()
    graph = client.get("/api/graph", params={"investigation_id": inv["id"]}, headers=auth(investigator_token))
    assert graph.status_code == 200
    assert graph.json()["nodes"] == []
    assert graph.json()["edges"] == []


# ---------------------------------------------------------------------------
# Existing analytics engine, exercised through the new scoped path
# ---------------------------------------------------------------------------

def test_analytics_dashboard_works_scoped_and_unscoped(client, investigator_token):
    # Unscoped: identical to pre-Phase-1 behavior (no investigation_id).
    unscoped = client.get("/api/analytics/dashboard", headers=auth(investigator_token))
    assert unscoped.status_code == 200
    assert "top_influencers" in unscoped.json()

    inv, case = _make_investigation_and_case(client, investigator_token, name="Analytics Scope Test")
    client.post(f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
                headers=auth(investigator_token), data={"source_type": "FIR"},
                files={"file": ("hub.txt", io.BytesIO(
                    b"Vikas Joshi called Anil Kapoor. Vikas Joshi called Rohit Sharma. "
                    b"Vikas Joshi called Meena Iyer."), "text/plain")})

    scoped = client.get("/api/analytics/dashboard", params={"investigation_id": inv["id"]},
                         headers=auth(investigator_token))
    assert scoped.status_code == 200
    body = scoped.json()
    assert body["total_entities"] > 0
    # The hub (Vikas Joshi) should be the top-ranked influencer in this tiny scoped graph.
    assert body["top_influencers"][0]["entity"]["label"] == "Vikas Joshi"


def test_audit_log_is_admin_only(client, investigator_token, admin_token):
    forbidden = client.get("/api/audit", headers=auth(investigator_token))
    assert forbidden.status_code == 403
    allowed = client.get("/api/audit", headers=auth(admin_token))
    assert allowed.status_code == 200
    assert isinstance(allowed.json(), list)


def test_audit_log_persists_investigation_actions(client, investigator_token, admin_token):
    inv = client.post("/api/investigations", json={"name": "Audited Investigation"},
                       headers=auth(investigator_token)).json()
    entries = client.get("/api/audit", headers=auth(admin_token)).json()
    assert any(e["action"] == "CREATE_INVESTIGATION" and e["target"] == inv["id"] for e in entries)
