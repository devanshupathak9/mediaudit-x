"""
Claim Q&A chat -- lets a reviewer ask free-text questions about a specific
claim ("was step therapy met?", "any drug interactions?", "why was this
denied?") and get a real, tool-grounded answer instead of canned text.

Reuses the same LLM client, tool schema, and tool dispatcher as the
adjudication agent (orchestrator.py) -- same zero-hallucination principle:
the model may only state what the claim record, a prior adjudication
result, or a live tool call actually returned this turn, never invent an
answer. Unlike adjudicate_claim, this never writes adjudication-results,
the audit ledger, or the claim's status -- it's read-only Q&A, not a new
decision.

The full claim/adjudication context is re-sent on every turn rather than
relying on the model to remember it from earlier in the conversation --
the frontend only keeps {role, content} text per turn (no tool-use
blocks), so re-grounding every turn is what keeps a 3rd or 4th question
in a conversation just as accurate as the 1st, at the cost of a few
hundred extra tokens per call.
"""
import json

from app.agent.orchestrator import TOOLS, _get_patient_clinical_summary, _run_tool
from app.llm_client import make_llm_client

MAX_CHAT_TOOL_ROUNDS = 3

_SOURCE_TYPE_MAP = {
    "medical-policies": "policy",
    "fhir-clinical-ehr": "clinical_note",
    "fda-drug-interactions": "drug_interaction",
}

SYSTEM_PROMPT = (
    "You are the MediAudit-X claim assistant, helping an insurance "
    "reviewer understand ONE specific claim. You have the claim record, "
    "its most recent adjudication result (if any), and three tools that "
    "query real clinical/policy/drug-interaction data. Answer only from "
    "the claim record, the adjudication result, or a tool call you make "
    "this turn -- never guess or state a fact you cannot trace to one of "
    "those sources. If the claim has already been adjudicated, prefer "
    "citing that result over re-running a tool, unless the reviewer is "
    "specifically asking you to verify or re-check something. If you "
    "don't have enough information to answer, say so plainly instead of "
    "guessing. Keep answers concise -- a reviewer is reading this while "
    "working a queue, not requesting a report."
)


def _citation_from_tool_result(tool_name: str, result: dict) -> list[dict]:
    """Shape matches what the frontend's AIAgentChat.tsx already renders:
    {id, type, description} -- built from what a tool actually returned
    this turn, distinct from orchestrator.py's own cited_evidence shape
    (different field names, used for adjudication-results instead)."""
    citations = []
    hits = result.get("hits", {}).get("hits", []) if isinstance(result, dict) else []
    for hit in hits[:3]:
        src = hit.get("_source", {})
        index = hit.get("_index", "")
        citation_type = _SOURCE_TYPE_MAP.get(index, tool_name)
        if index == "medical-policies":
            description = f"{src.get('policy_id', hit.get('_id'))} — {src.get('title', '')}"
        elif index == "fda-drug-interactions":
            description = f"{src.get('drug_a_name')} + {src.get('drug_b_name')}: {src.get('mechanism', '')}"
        else:
            description = src.get("code_display") or str(hit.get("_id"))
        citations.append({"id": str(hit.get("_id")), "type": citation_type, "description": description})

    if tool_name == "query_patient_clinical_trajectory" and isinstance(result, dict) and "step_therapy_met" in result:
        citations.append({
            "id": f"trajectory:{result.get('total_conservative_encounters', 0)}",
            "type": "clinical_trajectory",
            "description": (
                f"{result.get('total_conservative_encounters', 0)} conservative-therapy encounter(s), "
                f"{result.get('therapy_duration_days', 0)}d of {result.get('required_duration_days', 0)}d required"
            ),
        })
    return citations


def _citations_from_cited_evidence(cited_evidence: list[dict]) -> list[dict]:
    """Maps an existing adjudication's own cited_evidence (source_index/
    source_id/excerpt) into the frontend's {id, type, description} shape
    -- used as a fallback so a question answered purely from an already-
    computed adjudication result (no fresh tool call this turn) still
    populates the UI's citation list instead of showing none."""
    citations = []
    for item in cited_evidence or []:
        index = item.get("source_index", "")
        citations.append({
            "id": str(item.get("source_id", "")),
            "type": _SOURCE_TYPE_MAP.get(index, index or "evidence"),
            "description": item.get("excerpt", "")[:200],
        })
    return citations


def _claim_and_adjudication_context(claim: dict, adjudication: dict | None) -> str:
    lines = [f"Claim record:\n{json.dumps(claim, default=str)}"]
    if adjudication:
        lines.append(
            "Most recent adjudication result (already decided -- do not "
            "re-derive unless the reviewer asks you to verify it):\n"
            f"status={adjudication.get('status')}\n"
            f"matched_policy={json.dumps(adjudication.get('matched_policy'), default=str)}\n"
            f"trajectory_result={json.dumps(adjudication.get('trajectory_result'), default=str)}\n"
            f"cited_evidence={json.dumps(adjudication.get('cited_evidence'), default=str)}\n"
            f"generated_letter:\n{adjudication.get('generated_letter')}"
        )
    else:
        lines.append("No adjudication has been run for this claim yet.")
    return "\n\n".join(lines)


def answer_claim_question(
    claim: dict, adjudication: dict | None, question: str, history: list[dict],
) -> tuple[str, list[dict], bool]:
    """Returns (answer_text, citations, llm_used). Falls back to a plain,
    honest "no LLM configured" message (not a guess) if no LLM client is
    available, consistent with the rest of this codebase's fallback rule
    (see orchestrator._deterministic_tool_sweep for the adjudication-side
    equivalent)."""
    client, model_id = make_llm_client()
    if client is None:
        return (
            "No LLM is currently configured for this deployment, so I can't "
            "answer free-text questions right now. Here's what's on file for "
            f"this claim: status={claim.get('status')}, payer={claim.get('payer_name')}, "
            f"CPT={claim.get('cpt_code')}, ICD-10={claim.get('icd10_code')}.",
            [],
            False,
        )

    context = _claim_and_adjudication_context(claim, adjudication)
    clinical_summary = _get_patient_clinical_summary(claim.get("patient_id", ""))

    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append({
        "role": "user",
        "content": (
            f"{context}\n\nPatient's recent encounter/medication history "
            f"(for situational awareness -- verify anything decision-relevant "
            f"with a tool call, don't just take this summary's word for it):\n"
            f"{clinical_summary}\n\nReviewer's question: {question}"
        ),
    })

    citations: list[dict] = []
    for _round in range(MAX_CHAT_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model=model_id, max_tokens=1024, system=SYSTEM_PROMPT,
                tools=TOOLS, messages=messages,
            )
        except Exception as e:  # noqa: BLE001
            return f"The AI assistant hit an error answering that: {e}", citations, True

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_uses:
            answer = "\n\n".join(b.text for b in text_blocks if b.text.strip())
            if not citations and adjudication:
                # No fresh tool call this turn -- fall back to the
                # existing adjudication's own evidence so the UI's
                # citation list isn't empty just because the answer drew
                # on already-computed results instead of a live lookup.
                citations = _citations_from_cited_evidence(adjudication.get("cited_evidence", []))
            return answer or "I don't have enough information to answer that.", citations, True

        messages.append({"role": "assistant", "content": response.content})
        tool_results_content = []
        for tool_use in tool_uses:
            try:
                result = _run_tool(tool_use.name, dict(tool_use.input))
                citations.extend(_citation_from_tool_result(tool_use.name, result))
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            tool_results_content.append({
                "type": "tool_result", "tool_use_id": tool_use.id,
                "content": json.dumps(result, default=str)[:4000],
            })
        messages.append({"role": "user", "content": tool_results_content})

    return "I looked into that but couldn't reach a final answer in the tool-call budget allotted.", citations, True
