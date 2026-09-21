"""
Provisions the Agent Builder tools + agent this project uses for claim
chat. Idempotent (create-or-update), same pattern as
app/indices/create_indices.py -- safe to re-run any time the ES|QL
queries or agent instructions change.

Run with: python -m app.setup_agent_builder

The 3 custom tools mirror the existing Bedrock-based tool-loop
(app/tools/trajectory_tool.py, policy_matcher_tool.py,
drug_interaction_tool.py) closely enough for a reviewer's Q&A use case,
but are NOT byte-for-byte ports of that Python logic -- trajectory
duration math and RRF-fused policy ranking are still Python-side-only.
mediaudit_patient_history instead hands the agent the raw encounter
timeline and lets it reason over the dates itself; that reasoning is
visible in the converse response's `steps`, which is arguably more
transparent for a chat/explain use case than a hidden Python
computation, even though it means this path and the deterministic
adjudication path could theoretically disagree on a step-therapy
judgment call for the same patient. Fine for read-only Q&A; do not
reuse these tools for the adjudication decision itself.
"""
from app.agent_builder_client import upsert_agent, upsert_esql_tool

PATIENT_HISTORY_TOOL = "mediaudit_patient_history"
POLICY_SEARCH_TOOL = "mediaudit_search_policies"
DRUG_INTERACTION_TOOL = "mediaudit_search_drug_interactions"
AGENT_ID = "mediaudit-claim-assistant"

INSTRUCTIONS = (
    "You are the MediAudit Claim Assistant, helping an insurance reviewer "
    "understand a specific insurance claim. Every question you receive "
    "will include the claim record (patient_id, payer_name, cpt_code, "
    "icd10_code, status) and, if one exists, the most recent AI "
    "adjudication result (matched policy, trajectory result, cited "
    "evidence, decision letter) as context at the start of the message. "
    "\n\n"
    "Answer only from that context or from a tool call you make this "
    "turn -- never guess or state a fact you cannot trace to one of "
    "those sources. Use mediaudit_patient_history to check a patient's "
    "encounter/condition/medication timeline (e.g. for step-therapy or "
    "conservative-treatment questions), mediaudit_search_policies to "
    "look up a payer's coverage policy, and mediaudit_search_drug_interactions "
    "to check whether two medications have a known interaction. If the "
    "claim has already been adjudicated, prefer citing that existing "
    "result over re-deriving it from scratch, unless the reviewer "
    "specifically asks you to verify or re-check something. If you don't "
    "have enough information to answer, say so plainly instead of "
    "guessing. Keep answers concise -- a reviewer is reading this while "
    "working a queue, not requesting a report."
)


def setup() -> None:
    upsert_esql_tool(
        PATIENT_HISTORY_TOOL,
        description=(
            "Returns a patient's clinical encounter/condition/medication "
            "history in chronological order, for checking things like "
            "conservative-therapy/step-therapy timelines or active "
            "medications. Verified against real Synthea-generated patient "
            "data in fhir-clinical-ehr."
        ),
        query=(
            "FROM fhir-clinical-ehr "
            "| WHERE patient_id == ?patientId "
            "| KEEP timestamp, resource_type, code_display, clinician_notes "
            "| SORT timestamp ASC "
            "| LIMIT 200"
        ),
        params={"patientId": {"type": "string", "description": "The patient_id from the claim record"}},
    )

    upsert_esql_tool(
        POLICY_SEARCH_TOOL,
        description=(
            "Looks up a payer's coverage policy (title, CPT/ICD codes "
            "covered, clinical indications, whether step therapy is "
            "required) by exact payer name. Verified against real CMS "
            "Medicare LCDs and sample commercial payer policies in "
            "medical-policies."
        ),
        query=(
            "FROM medical-policies "
            "| WHERE payer_name == ?payer "
            "| KEEP policy_id, title, payer_name, cpt_codes, icd10_codes, "
            "clinical_indications, contraindications, step_therapy_required "
            "| LIMIT 20"
        ),
        params={"payer": {
            "type": "string",
            "description": "Exact payer_name from the claim record, e.g. 'UnitedHealthcare' or 'Medicare (CMS Local Coverage Determination)'",
        }},
    )

    upsert_esql_tool(
        DRUG_INTERACTION_TOOL,
        description=(
            "Checks whether a drug name (brand or generic) has any known "
            "FDA-flagged interaction on file, and with what other drug. "
            "Verified against real fda-drug-interactions records."
        ),
        query=(
            "FROM fda-drug-interactions "
            "| WHERE MATCH(drug_a_name, ?drugName) OR MATCH(drug_b_name, ?drugName) "
            "| KEEP drug_a_name, drug_b_name, severity, mechanism, fda_citation "
            "| LIMIT 20"
        ),
        params={"drugName": {"type": "string", "description": "A drug name, brand or generic"}},
    )

    upsert_agent(
        AGENT_ID,
        name="MediAudit Claim Assistant",
        description="Answers a reviewer's questions about a specific insurance claim using real clinical, policy, and drug-interaction data.",
        instructions=INSTRUCTIONS,
        tool_ids=[
            PATIENT_HISTORY_TOOL, POLICY_SEARCH_TOOL, DRUG_INTERACTION_TOOL,
            "platform.core.get_document_by_id", "platform.core.search",
        ],
    )
    print(f"Provisioned tools ({PATIENT_HISTORY_TOOL}, {POLICY_SEARCH_TOOL}, {DRUG_INTERACTION_TOOL}) and agent {AGENT_ID!r}")


if __name__ == "__main__":
    setup()
