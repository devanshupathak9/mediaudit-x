"""
Tests for app/agent_builder_client.py and app/agent/chat_agent_builder.py.

No live Kibana call in these tests -- HTTP is mocked. The API shapes
mocked here (tool-conflict response, tool_call step structure) were
verified against the real Agent Builder API on this project's Kibana
instance during development (see app/setup_agent_builder.py), not
guessed from documentation alone.
"""
from app.agent.chat_agent_builder import (
    _citations_from_steps,
    _rows_from_tool_call,
    answer_claim_question_via_agent_builder,
)
from app.agent_builder_client import AgentBuilderError, _already_exists


def test_already_exists_matches_real_conflict_shape():
    # Verified live: the API returns plain 400, not 409, for a duplicate id.
    e = AgentBuilderError(400, '{"message":"Tool with id mediaudit_patient_history already exists"}')
    assert _already_exists(e) is True


def test_already_exists_false_for_other_400s():
    e = AgentBuilderError(400, '{"message":"Invalid configuration for tool type esql"}')
    assert _already_exists(e) is False


def test_already_exists_false_for_other_status_codes():
    e = AgentBuilderError(503, "already exists")
    assert _already_exists(e) is False


# Real shape captured from a live converse() call against
# mediaudit_search_policies during development.
REAL_POLICY_TOOL_CALL_STEP = {
    "type": "tool_call",
    "tool_id": "mediaudit_search_policies",
    "params": {"payer": "Medicare (CMS Local Coverage Determination)"},
    "results": [
        {"type": "query", "data": {"esql": "FROM medical-policies | ..."}},
        {
            "type": "esql_results",
            "data": {
                "columns": [
                    {"name": "policy_id", "type": "keyword"},
                    {"name": "title", "type": "text"},
                    {"name": "step_therapy_required", "type": "boolean"},
                ],
                "values": [
                    ["POL-MEDICARE-LCD-36575", "Total Knee Arthroplasty", False],
                    ["POL-MEDICARE-LCD-34163", "Total Hip Arthroplasty", False],
                ],
            },
        },
    ],
}


def test_rows_from_tool_call_extracts_tabular_rows_not_the_query_entry():
    rows = _rows_from_tool_call(REAL_POLICY_TOOL_CALL_STEP)
    assert rows == [
        {"policy_id": "POL-MEDICARE-LCD-36575", "title": "Total Knee Arthroplasty", "step_therapy_required": False},
        {"policy_id": "POL-MEDICARE-LCD-34163", "title": "Total Hip Arthroplasty", "step_therapy_required": False},
    ]


def test_rows_from_tool_call_handles_no_tabular_results():
    step = {"type": "tool_call", "tool_id": "x", "results": [{"type": "query", "data": {"esql": "..."}}]}
    assert _rows_from_tool_call(step) == []


def test_citations_from_steps_maps_known_tool_with_real_field_names():
    citations = _citations_from_steps([REAL_POLICY_TOOL_CALL_STEP])
    assert len(citations) == 2
    assert citations[0] == {
        "id": "POL-MEDICARE-LCD-36575", "type": "policy",
        "description": "POL-MEDICARE-LCD-36575 — Total Knee Arthroplasty",
    }


def test_citations_from_steps_ignores_non_tool_call_steps():
    steps = [{"type": "reasoning", "reasoning": "thinking..."}]
    assert _citations_from_steps(steps) == []


def test_citations_from_steps_caps_rows_per_tool_call():
    many_rows_step = dict(REAL_POLICY_TOOL_CALL_STEP)
    many_rows_step["results"] = [{
        "type": "esql_results",
        "data": {
            "columns": [{"name": "policy_id", "type": "keyword"}],
            "values": [[f"POL-{i}"] for i in range(10)],
        },
    }]
    citations = _citations_from_steps([many_rows_step])
    assert len(citations) == 3  # _MAX_CITATIONS_PER_TOOL_CALL


def test_citations_from_steps_falls_back_generically_for_unknown_tools():
    step = {
        "type": "tool_call", "tool_id": "platform.core.search",
        "results": [{"type": "tabular_data", "data": {
            "columns": [{"name": "name", "type": "text"}, {"name": "id", "type": "keyword"}],
            "values": [["Some Doc", "DOC-1"]],
        }}],
    }
    citations = _citations_from_steps([step])
    assert len(citations) == 1
    assert citations[0]["type"] == "platform.core.search"
    assert "name=Some Doc" in citations[0]["description"]


def test_answer_claim_question_via_agent_builder_first_turn_sends_full_context(monkeypatch):
    import app.agent.chat_agent_builder as module
    captured = {}

    def fake_converse(agent_id, input_text, conversation_id=None):
        captured["input_text"] = input_text
        captured["conversation_id"] = conversation_id
        return {
            "status": "completed", "conversation_id": "conv-1",
            "response": {"message": "Here's the answer."}, "steps": [],
        }

    monkeypatch.setattr(module, "converse", fake_converse)

    answer, citations, conversation_id = answer_claim_question_via_agent_builder(
        claim={"claim_id": "CLM-1", "status": "PENDING"}, adjudication=None,
        question="Was step therapy met?", conversation_id=None,
    )

    assert answer == "Here's the answer."
    assert conversation_id == "conv-1"
    assert "Was step therapy met?" in captured["input_text"]
    assert "Claim record" in captured["input_text"]  # full context sent on first turn


def test_answer_claim_question_via_agent_builder_followup_turn_sends_only_question(monkeypatch):
    import app.agent.chat_agent_builder as module
    captured = {}

    def fake_converse(agent_id, input_text, conversation_id=None):
        captured["input_text"] = input_text
        return {"status": "completed", "conversation_id": "conv-1", "response": {"message": "ok"}, "steps": []}

    monkeypatch.setattr(module, "converse", fake_converse)

    answer_claim_question_via_agent_builder(
        claim={"claim_id": "CLM-1"}, adjudication=None,
        question="What severity is that?", conversation_id="conv-1",
    )

    assert captured["input_text"] == "What severity is that?"  # no re-sent context


def test_answer_claim_question_via_agent_builder_falls_back_to_existing_evidence(monkeypatch):
    import app.agent.chat_agent_builder as module

    monkeypatch.setattr(module, "converse", lambda *a, **kw: {
        "status": "completed", "conversation_id": "conv-1",
        "response": {"message": "Answered from existing context."}, "steps": [],  # no tool calls this turn
    })

    adjudication = {"cited_evidence": [
        {"source_index": "medical-policies", "source_id": "POL-9", "excerpt": "policy text"},
    ]}
    answer, citations, _ = answer_claim_question_via_agent_builder(
        claim={"claim_id": "CLM-1"}, adjudication=adjudication, question="Why?", conversation_id=None,
    )

    assert citations == [{"id": "POL-9", "type": "policy", "description": "policy text"}]


def test_answer_claim_question_via_agent_builder_raises_on_incomplete_status(monkeypatch):
    import app.agent.chat_agent_builder as module
    monkeypatch.setattr(module, "converse", lambda *a, **kw: {"status": "awaiting_prompt"})

    try:
        answer_claim_question_via_agent_builder({"claim_id": "CLM-1"}, None, "Q", None)
        assert False, "expected AgentBuilderError"
    except AgentBuilderError:
        pass
