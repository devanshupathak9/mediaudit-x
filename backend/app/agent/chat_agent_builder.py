"""
Claim Q&A via Elastic Agent Builder -- an alternative to chat.py's
hand-rolled Bedrock/Anthropic tool loop. Kibana's own agent/tool
orchestration runs the conversation and picks its own configured LLM
connector (this project has native Anthropic Claude connectors set up,
verified live -- see app/agent_builder_client.py); the 3 custom tools it
calls are provisioned by app/setup_agent_builder.py.

Unlike chat.py, conversation state is server-side in Agent Builder
(conversation_id), so only the latest question needs to be sent, not the
full prior history -- see routers/chat.py for how the two paths differ
at the HTTP layer as a result.

Real trade-off worth knowing (found during development, not theoretical):
mediaudit_patient_history hands the LLM the raw encounter timeline and
lets it reason over conservative-therapy evidence itself, which surfaced
a real NSAID prescription (Naproxen) that the deterministic
query_patient_clinical_trajectory tool's keyword search missed (it only
matches literal phrases like "NSAID" in the text, not drug-class
knowledge). That's a feature for an explain-it-to-a-reviewer chat, and
exactly why this must stay a read-only Q&A path -- never substitute it
for adjudicate_claim's deterministic decision logic.
"""
from app.agent.chat import _citations_from_cited_evidence, _claim_and_adjudication_context
from app.agent_builder_client import AgentBuilderError, converse
from app.setup_agent_builder import AGENT_ID

_POLICY_DESCRIPTION = lambda row: f"{row.get('policy_id')} — {row.get('title', '')}"
_DRUG_DESCRIPTION = lambda row: f"{row.get('drug_a_name')} + {row.get('drug_b_name')}: {row.get('mechanism', '')}"
_HISTORY_DESCRIPTION = lambda row: f"{row.get('timestamp')}: {row.get('resource_type')} — {row.get('code_display')}"

_TOOL_CITATION_SHAPE = {
    "mediaudit_search_policies": ("policy", "policy_id", _POLICY_DESCRIPTION),
    "mediaudit_search_drug_interactions": ("drug_interaction", None, _DRUG_DESCRIPTION),
    "mediaudit_patient_history": ("clinical_note", None, _HISTORY_DESCRIPTION),
}
_MAX_CITATIONS_PER_TOOL_CALL = 3


def _rows_from_tool_call(step: dict) -> list[dict]:
    """A tool_call step's `results` list mixes a "query" entry (the ES|QL
    text) with a tabular-data entry (columns + values) -- this pulls out
    just the rows as {column_name: value} dicts, regardless of which
    exact type label the tabular entry carries (verified as "esql_results"
    in isolation but not worth hard-coding that string here)."""
    rows = []
    for result in step.get("results", []):
        data = result.get("data", {})
        columns = data.get("columns")
        values = data.get("values")
        if not columns or values is None:
            continue
        names = [c["name"] for c in columns]
        rows.extend(dict(zip(names, row)) for row in values)
    return rows


def _citations_from_steps(steps: list[dict]) -> list[dict]:
    citations = []
    for step in steps:
        if step.get("type") != "tool_call":
            continue
        tool_id = step.get("tool_id", "")
        shape = _TOOL_CITATION_SHAPE.get(tool_id)
        rows = _rows_from_tool_call(step)
        for row in rows[:_MAX_CITATIONS_PER_TOOL_CALL]:
            if shape:
                citation_type, id_field, describe = shape
                row_id = str(row.get(id_field)) if id_field else f"{tool_id}:{hash(str(row)) & 0xFFFF}"
                description = describe(row)
            else:
                citation_type = tool_id
                row_id = f"{tool_id}:{hash(str(row)) & 0xFFFF}"
                description = ", ".join(f"{k}={v}" for k, v in list(row.items())[:3])
            citations.append({"id": row_id, "type": citation_type, "description": description[:300]})
    return citations


def answer_claim_question_via_agent_builder(
    claim: dict, adjudication: dict | None, question: str, conversation_id: str | None,
) -> tuple[str, list[dict], str | None]:
    """Returns (answer_text, citations, conversation_id). Raises
    AgentBuilderError on failure -- routers/chat.py catches it and falls
    back to the Bedrock-based chat.answer_claim_question, same
    "always have a deterministic/working fallback" rule this codebase
    uses everywhere an LLM/external provider is involved."""
    context = _claim_and_adjudication_context(claim, adjudication)
    # Full context every turn is not needed here (unlike chat.py) since
    # Agent Builder keeps server-side conversation state via
    # conversation_id -- only resend it on the first turn of a
    # conversation.
    input_text = question if conversation_id else f"{context}\n\nReviewer's question: {question}"

    result = converse(AGENT_ID, input_text, conversation_id=conversation_id)

    if result.get("status") != "completed":
        raise AgentBuilderError(0, f"Agent Builder did not complete: {result.get('status')}")

    answer = result.get("response", {}).get("message", "")
    citations = _citations_from_steps(result.get("steps", []))
    if not citations and adjudication:
        # No fresh tool call this turn (e.g. the agent answered from the
        # injected adjudication context) -- fall back to that
        # adjudication's own evidence so the UI's citation list isn't
        # empty just because nothing new was looked up. Same rule as
        # chat.py's Bedrock path.
        citations = _citations_from_cited_evidence(adjudication.get("cited_evidence", []))
    return answer, citations, result.get("conversation_id")
