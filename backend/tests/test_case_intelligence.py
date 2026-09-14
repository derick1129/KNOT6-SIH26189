"""
KNOT6 Case Intelligence tests: the deterministic summary, universal search,
conversation persistence/isolation, grounded retrieval, citation validation,
and graceful AI-provider-unavailable behavior.

The real HTTP endpoints are exercised throughout (via the FastAPI
TestClient, same as test_phase1_investigations.py). Where a test needs the
copilot to actually produce an answer, `app.copilot.copilot.get_llm_provider`
is monkeypatched to a small `FakeLLMProvider` test double -- no real network
call is made, and `InvestigationCopilot`'s dependency-injected `llm`
parameter is exactly the seam this is meant to exercise (see
app/copilot/llm_provider.py's docstring: "swapping providers is a one-file
change"). With no monkeypatch, the real `NullLLMProvider` is in effect
(no ANTHROPIC_API_KEY in the test environment), which is itself the subject
of `test_copilot_unavailable_without_provider`.
"""
from __future__ import annotations

import io
import re

import pytest

from app.copilot.llm_provider import LLMProvider
from tests.conftest import auth


class FakeLLMProvider(LLMProvider):
    """Echoes back the first real evidence citation code it was given (if
    any) plus a fabricated one, so tests can assert the fabricated one never
    survives server-side validation. Also records every prompt it received
    so a test can assert what context leaked into it (e.g. investigation
    isolation)."""
    available = True

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user_message: str) -> str:
        self.calls.append((system, user_message))
        real_codes = re.findall(r"\[EV-[0-9a-fA-F]{6,10}\]", user_message)
        real = real_codes[0] if real_codes else ""
        return (f"This is a grounded, investigative-lead-only answer. {real} "
                f"It also tries to cite a fabricated source [EV-00000000], which must not survive.")


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.copilot.copilot.get_llm_provider", lambda: fake)
    return fake


def _make_investigation_and_case(client, token, name):
    inv = client.post("/api/investigations", json={"name": name}, headers=auth(token)).json()
    case = client.post(f"/api/investigations/{inv['id']}/cases",
                        json={"case_number": f"CI-{inv['id'][:8]}", "title": "Case Intelligence test case"},
                        headers=auth(token)).json()
    return inv, case


def _upload_fir(client, token, inv, case, text: str, filename="fir.txt"):
    return client.post(
        f"/api/investigations/{inv['id']}/cases/{case['id']}/evidence",
        headers=auth(token), data={"source_type": "FIR", "description": "unit test FIR"},
        files={"file": (filename, io.BytesIO(text.encode()), "text/plain")},
    )


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def test_intelligence_search_copilot_conversations_require_auth(client):
    inv_id = "does-not-matter"
    assert client.get(f"/api/investigations/{inv_id}/intelligence").status_code == 401
    assert client.get(f"/api/investigations/{inv_id}/search", params={"q": "x"}).status_code == 401
    assert client.post(f"/api/investigations/{inv_id}/copilot", json={"question": "x"}).status_code == 401
    assert client.get(f"/api/investigations/{inv_id}/conversations").status_code == 401


def test_intelligence_404_for_unknown_investigation(client, investigator_token):
    res = client.get("/api/investigations/does-not-exist/intelligence", headers=auth(investigator_token))
    assert res.status_code == 404


def test_viewer_can_read_intelligence_and_search(client, investigator_token, viewer_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Viewer Read Test")
    res = client.get(f"/api/investigations/{inv['id']}/intelligence", headers=auth(viewer_token))
    assert res.status_code == 200
    res = client.get(f"/api/investigations/{inv['id']}/search", params={"q": "a"}, headers=auth(viewer_token))
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Deterministic Case Intelligence summary -- real data, no LLM
# ---------------------------------------------------------------------------

def test_case_intelligence_summary_reflects_real_data(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Intelligence Summary Test")
    _upload_fir(client, investigator_token, inv, case,
                "Farhan Ali called Deepak Nair. Farhan Ali called Deepak Nair. "
                "Farhan Ali called Deepak Nair. Farhan Ali called Deepak Nair.")

    graph = client.get("/api/graph", params={"investigation_id": inv["id"]}, headers=auth(investigator_token)).json()
    assert len(graph["nodes"]) >= 2

    res = client.get(f"/api/investigations/{inv['id']}/intelligence", headers=auth(investigator_token))
    assert res.status_code == 200
    summary = res.json()

    assert summary["case_brief"]["total_entities"] == len(graph["nodes"])
    assert summary["case_brief"]["total_relations"] == len(graph["edges"])
    assert "entities" in summary["case_brief"]["summary"].lower() or "network" in summary["case_brief"]["summary"].lower()

    labels = {e["entity"]["label"] for e in summary["key_entities"]}
    assert "Farhan Ali" in labels or "Deepak Nair" in labels
    for e in summary["key_entities"]:
        assert e["relevance_label"] in (
            "High investigation relevance", "Moderate investigative interest",
            "Entity of investigative interest -- requires investigator review",
        )

    assert summary["evidence_summary"]["total"] == 1
    assert summary["evidence_summary"]["processed"] == 1
    assert summary["evidence_summary"]["integrity_verified"] is None  # honest Phase 4 gap, not fabricated

    assert summary["investigator_notes"]["available"] is False  # no notes system exists yet -- stated, not faked


def test_case_intelligence_summary_empty_investigation_is_honest(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Truly Empty"}, headers=auth(investigator_token)).json()
    res = client.get(f"/api/investigations/{inv['id']}/intelligence", headers=auth(investigator_token))
    assert res.status_code == 200
    summary = res.json()
    assert summary["case_brief"]["total_entities"] == 0
    assert summary["key_entities"] == []
    assert summary["key_relationships"] == []
    assert "no entities" in summary["case_brief"]["summary"].lower()


def test_recent_developments_include_evidence_upload(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Recent Dev Test")
    _upload_fir(client, investigator_token, inv, case, "Some FIR text with no notable entities.")
    res = client.get(f"/api/investigations/{inv['id']}/intelligence", headers=auth(investigator_token))
    kinds = {d["kind"] for d in res.json()["recent_developments"]}
    assert "UPLOAD_EVIDENCE" in kinds
    assert "CREATE_INVESTIGATION" in kinds


# ---------------------------------------------------------------------------
# Universal search -- real data, no LLM
# ---------------------------------------------------------------------------

def test_search_finds_entity_relationship_and_evidence(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Search Test")
    _upload_fir(client, investigator_token, inv, case, "Karthik Menon called Divya Rao near City Mall.")

    res = client.get(f"/api/investigations/{inv['id']}/search", params={"q": "Karthik Menon"},
                      headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert any(hit["entity"]["label"] == "Karthik Menon" for hit in body["entities"])
    assert len(body["related_entities"]) >= 1
    assert len(body["relationships"]) >= 1
    assert len(body["evidence"]) >= 1
    assert body["evidence"][0]["evidence"]["source_type"] == "FIR"


def test_search_isolated_between_investigations(client, investigator_token):
    inv_a, case_a = _make_investigation_and_case(client, investigator_token, "Search Isolation A")
    inv_b, case_b = _make_investigation_and_case(client, investigator_token, "Search Isolation B")
    _upload_fir(client, investigator_token, inv_a, case_a, "Naveen Kapoor called Rekha Iyer.")
    _upload_fir(client, investigator_token, inv_b, case_b, "Tanvi Shah called Arvind Menon.")

    res = client.get(f"/api/investigations/{inv_a['id']}/search", params={"q": "Tanvi Shah"},
                      headers=auth(investigator_token))
    assert res.json()["entities"] == []


def test_search_finds_own_conversation_history(client, investigator_token, fake_llm):
    inv, case = _make_investigation_and_case(client, investigator_token, "Search Conversation Test")
    _upload_fir(client, investigator_token, inv, case, "Karthik Menon called Divya Rao.")
    client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "Why is Karthik Menon important?"},
                headers=auth(investigator_token))

    res = client.get(f"/api/investigations/{inv['id']}/search", params={"q": "Karthik Menon"},
                      headers=auth(investigator_token))
    assert any("Karthik Menon" in hit["question"] for hit in res.json()["conversation"])


def test_clear_conversation_deletes_only_own_turns(client, investigator_token, analyst_token):
    """DELETE /conversations ("Clear conversation" in the Case Intelligence
    UI) removes only the calling user's own turns for this investigation --
    it must never delete another investigator's conversation, and it must
    never touch anything outside CopilotConversationTurn (no investigation/
    case/evidence/entity data exists to even check here, which is itself
    part of the guarantee: this endpoint has no way to reach it)."""
    inv, case = _make_investigation_and_case(client, investigator_token, "Clear Conversation Test")
    _upload_fir(client, investigator_token, inv, case, "Karthik Menon called Divya Rao.")

    client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is happening here?"},
                headers=auth(investigator_token))
    client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is happening here?"},
                headers=auth(analyst_token))

    assert len(client.get(f"/api/investigations/{inv['id']}/conversations",
                           headers=auth(investigator_token)).json()) == 1
    assert len(client.get(f"/api/investigations/{inv['id']}/conversations",
                           headers=auth(analyst_token)).json()) == 1

    res = client.delete(f"/api/investigations/{inv['id']}/conversations", headers=auth(investigator_token))
    assert res.status_code == 204

    assert client.get(f"/api/investigations/{inv['id']}/conversations",
                       headers=auth(investigator_token)).json() == []
    # The analyst's own conversation survives the investigator's clear.
    assert len(client.get(f"/api/investigations/{inv['id']}/conversations",
                           headers=auth(analyst_token)).json()) == 1

    # The investigation itself, and the evidence uploaded into it, are
    # untouched -- clearing conversation memory only ever deletes chat turns.
    still_there = client.get(f"/api/investigations/{inv['id']}/intelligence", headers=auth(investigator_token))
    assert still_there.status_code == 200
    assert still_there.json()["case_brief"]["total_entities"] > 0


def test_clear_conversation_requires_auth(client):
    assert client.delete("/api/investigations/does-not-exist/conversations").status_code == 401


def test_search_finds_hypothesis_and_is_isolated(client, investigator_token):
    inv_a, case_a = _make_investigation_and_case(client, investigator_token, "Search Hypothesis A")
    inv_b, case_b = _make_investigation_and_case(client, investigator_token, "Search Hypothesis B")
    client.post(f"/api/investigations/{inv_a['id']}/hypotheses",
                json={"title": "Zubair Khan smuggling network hypothesis"}, headers=auth(investigator_token))

    found = client.get(f"/api/investigations/{inv_a['id']}/search", params={"q": "smuggling"},
                        headers=auth(investigator_token))
    assert len(found.json()["hypotheses"]) == 1
    assert found.json()["hypotheses"][0]["title"] == "Zubair Khan smuggling network hypothesis"

    not_found = client.get(f"/api/investigations/{inv_b['id']}/search", params={"q": "smuggling"},
                            headers=auth(investigator_token))
    assert not_found.json()["hypotheses"] == []


# ---------------------------------------------------------------------------
# No LLM configured: deterministic answering for common question shapes,
# honest "not configured" for genuine free-form reasoning (no fake AI)
# ---------------------------------------------------------------------------

def test_copilot_deterministic_answer_for_empty_investigation_without_provider(client, investigator_token):
    """
    KNOT6 Case Intelligence 2.0: "What is happening here?" is one of the
    question shapes the deterministic answerer (app/copilot/deterministic_
    answerer.py) handles without an LLM -- it narrates the same real,
    non-fabricated case-brief text app/services/investigation_
    intelligence.py's build_case_brief already produces (see
    test_case_intelligence_summary_empty_investigation_is_honest). This
    supersedes the old "always unavailable" behavior for this specific
    question shape: a deterministic answer is a real answer, not a fake one,
    so it IS persisted to conversation history.
    """
    inv, case = _make_investigation_and_case(client, investigator_token, "No Provider Test")
    res = client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is happening here?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["mode"] == "deterministic"
    assert "no entities" in body["answer"].lower()
    assert body["turn_id"] is not None

    convo = client.get(f"/api/investigations/{inv['id']}/conversations", headers=auth(investigator_token))
    assert len(convo.json()) == 1


def test_copilot_still_unavailable_for_open_ended_reasoning_without_provider(client, investigator_token):
    """The "no fake AI" guarantee still holds: a question that isn't one of
    the recognized deterministic shapes (no resolvable entity, no
    resume/changed/signal/evidence/state keyword) gets the honest
    "not configured" message, not a guess -- and, exactly as before, does
    not pollute conversation history."""
    inv, case = _make_investigation_and_case(client, investigator_token, "Open Ended No Provider")
    _upload_fir(client, investigator_token, inv, case, "Some FIR text with no notable named entities.")
    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "Do you think this case will get solved?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert "KNOT6 AI reasoning is not configured" in body["answer"]
    assert body["citations"] == []
    assert body["turn_id"] is None

    convo = client.get(f"/api/investigations/{inv['id']}/conversations", headers=auth(investigator_token))
    assert convo.json() == []


def test_deterministic_financial_connections_filters_to_financial_edges_only(client, investigator_token):
    """
    "What about his financial connections?" (or any question naming the
    entity + a financial keyword) must filter the neighborhood down to real
    financial connections (TRANSACTED_WITH, or OWNS specifically targeting a
    FINANCIAL_ACCOUNT node) -- not fall through to the generic top-5
    connections list, which could bury the financial ones or, worse,
    surface an OWNS-a-phone/vehicle edge as if it were financial (OWNS is
    generic ownership; only an OWNS edge whose target is actually a
    FINANCIAL_ACCOUNT counts -- see app/copilot/deterministic_answerer.py's
    rule 6a).

    Built directly via the graph layer (like
    tests/test_integrity_and_resolution.py) rather than free-text NLP
    extraction, for the same reason: deterministic, not dependent on
    spaCy's small-model NER tagging this exact phrasing correctly.
    """
    inv, case = _make_investigation_and_case(client, investigator_token, "Financial Filter Test")

    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity, upsert_relation

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    person = upsert_entity(store, schema.PERSON, "Deepak Verma", "doc-a")
    phone = upsert_entity(store, schema.PHONE, "9000000000", "doc-a")
    account = upsert_entity(store, schema.FINANCIAL_ACCOUNT, "ACC9999", "doc-a")
    upsert_relation(store, person.id, phone.id, schema.OWNS, "doc-a")
    upsert_relation(store, person.id, account.id, schema.OWNS, "doc-a")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What are Deepak Verma's financial connections?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    answer = res.json()["answer"]
    assert "ACC9999" in answer
    assert "9000000000" not in answer  # the phone must NOT be reported as a financial connection


def test_deterministic_financial_connections_honest_when_none_exist(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "No Financial Connections Test")

    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity, upsert_relation

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    person = upsert_entity(store, schema.PERSON, "Zara Khan", "doc-a")
    phone = upsert_entity(store, schema.PHONE, "9111111111", "doc-a")
    upsert_relation(store, person.id, phone.id, schema.OWNS, "doc-a")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What are Zara Khan's financial connections?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    answer = res.json()["answer"].lower()
    assert "no financial connections" in answer


def test_deterministic_influencers_question_answered_without_llm(client, investigator_token):
    """Regression test: "Who are the most relevant entities?" (a PS worked
    example) previously fell through to the honest "not configured" reply
    because _classify_intent didn't recognize this phrasing as an
    INFLUENCERS question, and even when classified correctly no
    deterministic rule narrated the ranked list at all."""
    inv, case = _make_investigation_and_case(client, investigator_token, "Influencers Question")
    _upload_fir(client, investigator_token, inv, case,
                "Karthik Menon called Divya Rao. Divya Rao called Arjun Nair. Karthik Menon called Arjun Nair.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "Who are the most relevant entities?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["mode"] == "deterministic"
    assert "most relevant entities" in body["answer"].lower()
    assert "AI reasoning is not configured" not in body["answer"]


def test_state_question_not_hijacked_by_influencers_rule(client, investigator_token):
    """Regression test for a bug introduced (and caught) while fixing the
    above: the INFLUENCERS narration rule must be gated on the actual
    classified intent, not merely on `bundle.influencers` being non-empty --
    the no-entity GENERAL fallback also populates a top-5 influencers list,
    which briefly hijacked "What is happening in this investigation?" into
    an influencer ranking instead of the real case brief."""
    inv, case = _make_investigation_and_case(client, investigator_token, "State Question Test")
    _upload_fir(client, investigator_token, inv, case, "Karthik Menon called Divya Rao.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is happening in this investigation?"},
                       headers=auth(investigator_token))
    answer = res.json()["answer"].lower()
    assert "most relevant entities" not in answer
    assert "entities" in answer and "relationships" in answer  # the real case-brief sentence shape


def test_deterministic_temporal_question_narrates_timeline(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Temporal Question")

    from app.db.graph_store import ScopedGraphStore, get_graph_store
    from app.graph import schema
    from app.graph.graph_builder import upsert_entity, upsert_relation

    store = ScopedGraphStore(get_graph_store(), inv["id"])
    a = upsert_entity(store, schema.PERSON, "Temporal Person", "doc-a")
    loc = upsert_entity(store, schema.LOCATION, "Temporal Place", "doc-a")
    upsert_relation(store, a.id, loc.id, schema.PRESENT_AT, "doc-a", attributes={"document_date": "2026-02-01"})

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What happened around Temporal Person?"}, headers=auth(investigator_token))
    answer = res.json()["answer"]
    assert "Recorded events involving Temporal Person" in answer
    assert "Temporal Place" in answer


def test_copilot_hypothesis_question_narrates_real_hypothesis(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Copilot Hypothesis Question")
    ev = _upload_fir(client, investigator_token, inv, case, "Some report text.", filename="hyp_ev.txt").json()
    hyp = client.post(f"/api/investigations/{inv['id']}/hypotheses", json={"title": "Test coordination hypothesis"},
                       headers=auth(investigator_token)).json()
    client.post(f"/api/hypotheses/{hyp['id']}/evidence",
                json={"evidence_id": ev["id"], "relationship_type": "CONTRADICTING", "note": "Alibi"},
                headers=auth(investigator_token))

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What evidence contradicts this hypothesis?"}, headers=auth(investigator_token))
    body = res.json()
    assert body["mode"] == "deterministic"
    assert "Test coordination hypothesis" in body["answer"]
    assert "contradicts" in body["answer"].lower()
    assert any(a["type"] == "OPEN_HYPOTHESIS" and a["hypothesis_id"] == hyp["id"] for a in body["actions"])
    assert "is true" not in body["answer"].lower()


def test_copilot_hypothesis_question_honest_when_none_exist(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "No Hypothesis Yet")
    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What does the hypothesis say?"}, headers=auth(investigator_token))
    assert "no hypotheses" in res.json()["answer"].lower()


def test_deterministic_path_question(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Deterministic Path Test")
    _upload_fir(client, investigator_token, inv, case, "Records show Suresh Yadav transferred money to account 123456789012.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "Show me the path between Suresh Yadav and 123456789012."},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["mode"] == "deterministic"
    assert "Suresh Yadav" in body["answer"] and "123456789012" in body["answer"]
    assert any(a["type"] == "SHOW_PATH" for a in body["actions"])


def test_deterministic_evidence_follow_up_uses_prior_turn_entities(client, investigator_token):
    """Question #5 of the required test set: 'What evidence supports this
    connection?' has no pronoun at all -- this only works because
    InvestigationCopilot.answer() falls back to the previous turn's
    resolved entities whenever the current question resolves none, not just
    when a pronoun word is present."""
    inv, case = _make_investigation_and_case(client, investigator_token, "Evidence Followup Test")
    _upload_fir(client, investigator_token, inv, case, "Records show Suresh Yadav transferred money to account 123456789012.")

    first = client.post(f"/api/investigations/{inv['id']}/copilot",
                         json={"question": "Why is Suresh Yadav important?"}, headers=auth(investigator_token))
    assert first.json()["available"] is True

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What evidence supports this connection?"},
                       headers=auth(investigator_token))
    body = res.json()
    assert body["available"] is True
    assert body["citations"]


def test_deterministic_what_changed_since_last_review(client, investigator_token):
    inv, case = _make_investigation_and_case(client, investigator_token, "Changed Since Test")
    client.post(f"/api/investigations/{inv['id']}/copilot",
                json={"question": "What is happening in this investigation?"}, headers=auth(investigator_token))
    _upload_fir(client, investigator_token, inv, case, "Suresh Yadav called ACC1001.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What changed since my last review?"},
                       headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert "evidence" in body["answer"].lower() or "uploaded" in body["answer"].lower()


# ---------------------------------------------------------------------------
# Investigation activity: "continue where you left off"
# ---------------------------------------------------------------------------

def test_resume_point_empty_then_populated_after_activity(client, investigator_token):
    inv = client.post("/api/investigations", json={"name": "Resume Test"}, headers=auth(investigator_token)).json()

    empty = client.get(f"/api/investigations/{inv['id']}/resume", headers=auth(investigator_token))
    assert empty.status_code == 200
    assert empty.json()["available"] is False

    rec = client.post(f"/api/investigations/{inv['id']}/activity",
                       json={"activity_type": "ENTITY_VIEWED", "target_type": "ENTITY",
                             "target_id": "some-entity-id", "target_label": "Suresh Yadav"},
                       headers=auth(investigator_token))
    assert rec.status_code == 204

    populated = client.get(f"/api/investigations/{inv['id']}/resume", headers=auth(investigator_token))
    body = populated.json()
    assert body["available"] is True
    assert "Suresh Yadav" in body["description"]
    assert body["action"]["type"] == "OPEN_ENTITY"
    assert body["action"]["entity_id"] == "some-entity-id"


def test_resume_action_does_not_self_corrupt_when_clicked_repeatedly(client, investigator_token):
    """
    Regression test for a real bug found by clicking through the feature:
    frontend/src/components/ResumePanel.tsx's "Continue" button calls
    `runAction(resume.action)`, which re-records a fresh activity using
    `action.label` as the new `target_label`. `_resume_action`
    (app/services/activity.py) previously built that label as
    "Continue: {label}" -- so clicking "Continue" once corrupted the next
    resume point into "You were last reviewing Continue: X", and clicking
    it again would compound further ("Continue: Continue: X"). The action
    label must stay the plain entity label indefinitely, however many times
    the resume point is re-derived from a chain of re-recorded activities.
    """
    inv = client.post("/api/investigations", json={"name": "Resume No Corrupt"}, headers=auth(investigator_token)).json()
    client.post(f"/api/investigations/{inv['id']}/activity",
                json={"activity_type": "ENTITY_VIEWED", "target_type": "ENTITY",
                      "target_id": "ent-1", "target_label": "Suresh Yadav"},
                headers=auth(investigator_token))

    for _ in range(3):
        resume = client.get(f"/api/investigations/{inv['id']}/resume", headers=auth(investigator_token)).json()
        assert resume["description"] == "You were last reviewing Suresh Yadav."
        assert resume["action"]["label"] == "Suresh Yadav"
        # Simulate clicking "Continue": copilotActions.ts re-records the
        # same activity type using the action's own label/entity_id.
        client.post(f"/api/investigations/{inv['id']}/activity",
                    json={"activity_type": "ENTITY_VIEWED", "target_type": "ENTITY",
                          "target_id": resume["action"]["entity_id"], "target_label": resume["action"]["label"]},
                    headers=auth(investigator_token))


def test_activity_requires_auth_and_valid_investigation(client, investigator_token):
    assert client.post("/api/investigations/does-not-matter/activity", json={"activity_type": "ENTITY_VIEWED"}).status_code == 401
    assert client.get("/api/investigations/does-not-matter/resume").status_code == 401
    res = client.post("/api/investigations/does-not-exist/activity", json={"activity_type": "ENTITY_VIEWED"},
                       headers=auth(investigator_token))
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Grounded copilot: retrieval, citations, actions, conversation memory
# ---------------------------------------------------------------------------

def test_copilot_grounded_answer_has_valid_citation_and_actions(client, investigator_token, fake_llm):
    inv, case = _make_investigation_and_case(client, investigator_token, "Grounded Copilot Test")
    _upload_fir(client, investigator_token, inv, case,
                "Meera Kulkarni called Suresh Yadav. Meera Kulkarni called Suresh Yadav. "
                "Meera Kulkarni called Suresh Yadav.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "Why is Meera Kulkarni important?"}, headers=auth(investigator_token))
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["turn_id"] is not None

    # The fabricated citation the fake LLM tried to add must never survive.
    assert "EV-00000000" not in body["answer"]
    assert all(c["evidence_id"] != "00000000" for c in body["citations"])

    # A real, retrieved entity should produce a real navigation action.
    assert any(a["type"] in ("OPEN_ENTITY", "OPEN_GRAPH") for a in body["actions"])


def test_copilot_no_fabricated_citation_when_no_evidence_retrieved(client, investigator_token, fake_llm):
    inv = client.post("/api/investigations", json={"name": "No Evidence Copilot Test"},
                       headers=auth(investigator_token)).json()
    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "What is happening in this investigation?"},
                       headers=auth(investigator_token))
    body = res.json()
    assert body["available"] is True
    assert body["citations"] == []
    assert "EV-00000000" not in body["answer"]


def test_copilot_graph_path_question_returns_show_path_action(client, investigator_token, fake_llm):
    inv, case = _make_investigation_and_case(client, investigator_token, "Path Copilot Test")
    _upload_fir(client, investigator_token, inv, case, "Rohit Chatterjee called Anjali Bose.")

    res = client.post(f"/api/investigations/{inv['id']}/copilot",
                       json={"question": "How is Rohit Chatterjee connected to Anjali Bose?"},
                       headers=auth(investigator_token))
    body = res.json()
    assert body["available"] is True
    path_actions = [a for a in body["actions"] if a["type"] == "SHOW_PATH"]
    assert len(path_actions) == 1
    assert path_actions[0]["entity_id"] and path_actions[0]["target_entity_id"]


def test_copilot_never_leaks_another_investigations_data(client, investigator_token, fake_llm):
    inv_a, case_a = _make_investigation_and_case(client, investigator_token, "Copilot Isolation A")
    inv_b, case_b = _make_investigation_and_case(client, investigator_token, "Copilot Isolation B")
    _upload_fir(client, investigator_token, inv_a, case_a, "Ishaan Verma called Ritika Chopra.")
    _upload_fir(client, investigator_token, inv_b, case_b, "Zara Fernandes called Kabir Malhotra.")

    client.post(f"/api/investigations/{inv_a['id']}/copilot",
                json={"question": "What is happening in this investigation?"}, headers=auth(investigator_token))

    # Inspect exactly what the LLM was actually given for investigation A.
    _, prompt = fake_llm.calls[-1]
    assert "Zara Fernandes" not in prompt
    assert "Kabir Malhotra" not in prompt


def test_conversation_persists_and_pronoun_resolves_across_turns(client, investigator_token, fake_llm):
    inv, case = _make_investigation_and_case(client, investigator_token, "Pronoun Test")
    _upload_fir(client, investigator_token, inv, case,
                "Nikhil Bansal called Alok Mehra. Nikhil Bansal called Alok Mehra.")

    first = client.post(f"/api/investigations/{inv['id']}/copilot",
                         json={"question": "Why is Nikhil Bansal important?"}, headers=auth(investigator_token))
    assert first.json()["context_entity_ids"]

    second = client.post(f"/api/investigations/{inv['id']}/copilot",
                          json={"question": "What about his connections?"}, headers=auth(investigator_token))
    assert second.status_code == 200
    # The pronoun should resolve back to the entity from the first turn.
    _, second_prompt = fake_llm.calls[-1]
    assert "Nikhil Bansal" in second_prompt

    convo = client.get(f"/api/investigations/{inv['id']}/conversations", headers=auth(investigator_token)).json()
    assert len(convo) == 2
    assert convo[0]["question"] == "Why is Nikhil Bansal important?"
    assert convo[1]["question"] == "What about his connections?"


def test_user_a_cannot_retrieve_user_bs_conversation(client, investigator_token, analyst_token, fake_llm):
    inv, case = _make_investigation_and_case(client, investigator_token, "Conversation Isolation Test")
    _upload_fir(client, investigator_token, inv, case, "Devansh Rao called Pooja Iyer.")

    client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "Investigator-only question"},
                headers=auth(investigator_token))
    client.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "Analyst-only question"},
                headers=auth(analyst_token))

    investigator_convo = client.get(f"/api/investigations/{inv['id']}/conversations",
                                     headers=auth(investigator_token)).json()
    analyst_convo = client.get(f"/api/investigations/{inv['id']}/conversations",
                                headers=auth(analyst_token)).json()

    assert {t["question"] for t in investigator_convo} == {"Investigator-only question"}
    assert {t["question"] for t in analyst_convo} == {"Analyst-only question"}
