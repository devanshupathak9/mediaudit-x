"""
Tests for app/agent/chat.py (the claim Q&A logic) and routers/chat.py
(the HTTP layer). The LLM loop is tested against a fake client (no
network call, no real Bedrock credentials needed to run this file) --
real end-to-end behavior against live Bedrock was verified manually
against real claims (CLM-2003, CLM-2002) during development.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.chat import (
    _citation_from_tool_result,
    _citations_from_cited_evidence,
    answer_claim_question,
)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, input_: dict, id_: str = "tool-1"):
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    """Returns a scripted sequence of responses, one per .messages.create() call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


CLAIM = {"claim_id": "CLM-TEST", "patient_id": "PAT-TEST", "payer_name": "TestPayer",
         "cpt_code": "99213", "icd10_code": "M17.11", "status": "PENDING"}


def test_no_llm_configured_returns_honest_fallback(monkeypatch):
    import app.agent.chat as chat_module
    monkeypatch.setattr(chat_module, "make_llm_client", lambda: (None, None))

    answer, citations, llm_used = answer_claim_question(CLAIM, None, "Why?", [])

    assert llm_used is False
    assert citations == []
    assert "No LLM is currently configured" in answer
    assert "PENDING" in answer  # still surfaces real claim facts, not nothing


def test_text_only_response_returns_answer_no_tool_calls(monkeypatch):
    import app.agent.chat as chat_module
    fake_client = _FakeClient([_FakeResponse([_text_block("The claim looks fine.")])])
    monkeypatch.setattr(chat_module, "make_llm_client", lambda: (fake_client, "fake-model"))
    monkeypatch.setattr(chat_module, "_get_patient_clinical_summary", lambda patient_id: "(no history)")

    answer, citations, llm_used = answer_claim_question(CLAIM, None, "Is this claim okay?", [])

    assert llm_used is True
    assert answer == "The claim looks fine."
    assert citations == []
    assert len(fake_client.calls) == 1


def test_tool_use_round_then_final_answer_produces_citations(monkeypatch):
    import app.agent.chat as chat_module
    monkeypatch.setattr(chat_module, "_get_patient_clinical_summary", lambda patient_id: "(no history)")

    tool_call_response = _FakeResponse([_tool_use_block(
        "audit_drug_drug_contraindications",
        {"active_rxnorm_codes": ["Warfarin"], "new_medication_code": "Ciprofloxacin"},
    )])
    final_response = _FakeResponse([_text_block("Yes, a major interaction was found.")])
    fake_client = _FakeClient([tool_call_response, final_response])
    monkeypatch.setattr(chat_module, "make_llm_client", lambda: (fake_client, "fake-model"))

    fake_tool_result = {
        "hits": {"hits": [{
            "_id": "INT-3", "_index": "fda-drug-interactions",
            "_source": {"drug_a_name": "Warfarin", "drug_b_name": "Ciprofloxacin",
                        "mechanism": "CYP1A2 inhibition", "severity": "Major"},
        }]}
    }
    monkeypatch.setattr(chat_module, "_run_tool", lambda name, inp: fake_tool_result)

    answer, citations, llm_used = answer_claim_question(CLAIM, None, "Any interactions?", [])

    assert answer == "Yes, a major interaction was found."
    assert len(citations) == 1
    assert citations[0]["id"] == "INT-3"
    assert citations[0]["type"] == "drug_interaction"
    assert "Warfarin" in citations[0]["description"]
    assert len(fake_client.calls) == 2  # one tool round + one final round


def test_tool_call_error_is_reported_as_a_result_not_raised(monkeypatch):
    import app.agent.chat as chat_module
    monkeypatch.setattr(chat_module, "_get_patient_clinical_summary", lambda patient_id: "(no history)")
    monkeypatch.setattr(chat_module, "_run_tool", lambda name, inp: (_ for _ in ()).throw(RuntimeError("boom")))

    tool_call_response = _FakeResponse([_tool_use_block("query_patient_clinical_trajectory", {"patient_id": "x", "therapy_keywords": []})])
    final_response = _FakeResponse([_text_block("Couldn't verify that.")])
    fake_client = _FakeClient([tool_call_response, final_response])
    monkeypatch.setattr(chat_module, "make_llm_client", lambda: (fake_client, "fake-model"))

    answer, citations, llm_used = answer_claim_question(CLAIM, None, "Was step therapy met?", [])

    assert answer == "Couldn't verify that."  # loop continued instead of crashing
    assert citations == []


def test_exceeding_tool_round_budget_returns_honest_message(monkeypatch):
    import app.agent.chat as chat_module
    monkeypatch.setattr(chat_module, "_get_patient_clinical_summary", lambda patient_id: "(no history)")
    monkeypatch.setattr(chat_module, "_run_tool", lambda name, inp: {"hits": {"hits": []}})

    # Always returns another tool call, never a final text-only response --
    # forces the MAX_CHAT_TOOL_ROUNDS budget to be hit.
    always_tool_call = lambda **kw: _FakeResponse([_tool_use_block("match_payer_coverage_policy", {
        "payer": "x", "cpt_code": "1", "icd10_code": "M1", "clinical_summary": "s",
    })])
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: always_tool_call(**kw)))
    monkeypatch.setattr(chat_module, "make_llm_client", lambda: (fake_client, "fake-model"))

    answer, citations, llm_used = answer_claim_question(CLAIM, None, "Deep question", [])

    assert "couldn't reach a final answer" in answer
    assert llm_used is True


def test_llm_call_exception_is_caught_and_reported():
    import app.agent.chat as chat_module

    def _raise(**kwargs):
        raise ConnectionError("no network")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))
    import unittest.mock
    with unittest.mock.patch.object(chat_module, "make_llm_client", return_value=(fake_client, "fake-model")):
        with unittest.mock.patch.object(chat_module, "_get_patient_clinical_summary", return_value="(no history)"):
            answer, citations, llm_used = answer_claim_question(CLAIM, None, "Q", [])

    assert "hit an error" in answer
    assert citations == []
    assert llm_used is True


def test_citation_from_tool_result_maps_known_indices():
    result = {"hits": {"hits": [{
        "_id": "POL-1", "_index": "medical-policies",
        "_source": {"policy_id": "POL-1", "title": "Knee Coverage"},
    }]}}
    citations = _citation_from_tool_result("match_payer_coverage_policy", result)
    assert citations == [{"id": "POL-1", "type": "policy", "description": "POL-1 — Knee Coverage"}]


def test_citation_from_tool_result_adds_trajectory_summary():
    result = {"step_therapy_met": True, "total_conservative_encounters": 3,
              "therapy_duration_days": 200, "required_duration_days": 180}
    citations = _citation_from_tool_result("query_patient_clinical_trajectory", result)
    assert len(citations) == 1
    assert citations[0]["type"] == "clinical_trajectory"
    assert "3 conservative-therapy" in citations[0]["description"]


def test_citations_from_cited_evidence_maps_shape():
    cited_evidence = [
        {"source_index": "medical-policies", "source_id": "POL-9", "excerpt": "some policy text"},
        {"source_index": "fhir-clinical-ehr", "source_id": "PAT-1", "excerpt": "encounter note"},
    ]
    citations = _citations_from_cited_evidence(cited_evidence)
    assert citations[0] == {"id": "POL-9", "type": "policy", "description": "some policy text"}
    assert citations[1] == {"id": "PAT-1", "type": "clinical_note", "description": "encounter note"}


def test_citations_from_cited_evidence_handles_empty_list():
    assert _citations_from_cited_evidence([]) == []
    assert _citations_from_cited_evidence(None) == []


# ── router-level: request/response shape, 404, provider fallback ────────

def _build_test_app(
    monkeypatch, find_claim_result, adjudication_result, chat_result,
    chat_provider="bedrock", agent_builder_result=None, agent_builder_configured_=False,
):
    """Defaults to chat_provider="bedrock" and an unconfigured Agent
    Builder so these tests never make a real network call regardless of
    what's in .env -- tests that specifically want the Agent Builder path
    pass chat_provider="agent_builder" and agent_builder_configured_=True."""
    import app.routers.chat as chat_router

    monkeypatch.setattr(chat_router, "_find_claim", lambda es, claim_id: find_claim_result)
    monkeypatch.setattr(chat_router, "_latest_adjudication", lambda es, claim_id: adjudication_result)
    monkeypatch.setattr(chat_router, "get_es_client", lambda: object())
    monkeypatch.setattr(chat_router, "answer_claim_question", lambda **kw: chat_result)
    monkeypatch.setattr(chat_router.settings, "chat_provider", chat_provider)
    monkeypatch.setattr(chat_router, "agent_builder_configured", lambda: agent_builder_configured_)
    if agent_builder_result is not None:
        if isinstance(agent_builder_result, Exception):
            def _raise(**kw):
                raise agent_builder_result
            monkeypatch.setattr(chat_router, "answer_claim_question_via_agent_builder", _raise)
        else:
            monkeypatch.setattr(chat_router, "answer_claim_question_via_agent_builder", lambda **kw: agent_builder_result)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(chat_router.router)
    return app


def test_chat_endpoint_returns_answer_and_citations(monkeypatch):
    app = _build_test_app(
        monkeypatch,
        find_claim_result=CLAIM,
        adjudication_result=None,
        chat_result=("Yes.", [{"id": "X", "type": "policy", "description": "d"}], True),
    )
    resp = TestClient(app).post("/claims/CLM-TEST/chat", json={"question": "Is this okay?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Yes."
    assert body["citations"] == [{"id": "X", "type": "policy", "description": "d"}]
    assert body["provider"] == "bedrock"
    assert body["conversation_id"] is None


def test_chat_endpoint_uses_agent_builder_when_configured(monkeypatch):
    app = _build_test_app(
        monkeypatch, CLAIM, None, ("unused", [], True),
        chat_provider="agent_builder", agent_builder_configured_=True,
        agent_builder_result=("Agent Builder answer.", [{"id": "P-1", "type": "policy", "description": "d"}], "conv-123"),
    )
    resp = TestClient(app).post("/claims/CLM-TEST/chat", json={"question": "Q"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Agent Builder answer."
    assert body["provider"] == "agent_builder"
    assert body["conversation_id"] == "conv-123"


def test_chat_endpoint_falls_back_to_bedrock_when_agent_builder_errors(monkeypatch):
    from app.agent_builder_client import AgentBuilderError

    app = _build_test_app(
        monkeypatch, CLAIM, None, ("Bedrock fallback answer.", [], True),
        chat_provider="agent_builder", agent_builder_configured_=True,
        agent_builder_result=AgentBuilderError(503, "Kibana unreachable"),
    )
    resp = TestClient(app).post("/claims/CLM-TEST/chat", json={"question": "Q"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Bedrock fallback answer."
    assert body["provider"] == "bedrock"


def test_chat_endpoint_skips_agent_builder_when_not_configured(monkeypatch):
    app = _build_test_app(
        monkeypatch, CLAIM, None, ("Bedrock answer.", [], True),
        chat_provider="agent_builder", agent_builder_configured_=False,
    )
    resp = TestClient(app).post("/claims/CLM-TEST/chat", json={"question": "Q"})
    assert resp.json()["provider"] == "bedrock"


def test_chat_endpoint_404_when_claim_missing(monkeypatch):
    import app.routers.chat as chat_router
    from fastapi import FastAPI, HTTPException

    def _not_found(es, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")

    monkeypatch.setattr(chat_router, "_find_claim", _not_found)
    monkeypatch.setattr(chat_router, "get_es_client", lambda: object())
    app = FastAPI()
    app.include_router(chat_router.router)

    resp = TestClient(app).post("/claims/DOES-NOT-EXIST/chat", json={"question": "Q"})
    assert resp.status_code == 404


def test_chat_endpoint_rejects_empty_question(monkeypatch):
    app = _build_test_app(monkeypatch, CLAIM, None, ("A", [], True))
    resp = TestClient(app).post("/claims/CLM-TEST/chat", json={"question": ""})
    assert resp.status_code == 422
