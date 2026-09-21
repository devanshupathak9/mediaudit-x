"""
Step 4.4 unit tests — run against the sample fixture data in data/sample/.

BUILT LIVE (18 Sept). Requires a running Elasticsearch with sample data
already loaded (`python -m app.ingestion.load_sample_data`). Run with:

    cd backend && python -m pytest tests/ -v

These hit a real cluster rather than mocking Elasticsearch, matching the
build spec's "not mocked" requirement for the eventual eval script (Step
9) and to catch real query-shape bugs (e.g. retriever API availability)
before the demo does.
"""
import pytest

from app.tools.trajectory_tool import query_patient_clinical_trajectory
from app.tools.policy_matcher_tool import match_payer_coverage_policy_fallback
from app.tools.drug_interaction_tool import (
    audit_drug_drug_contraindications,
    resolve_medication_to_rxnorm,
)
from app.tools.audit_ledger import append_entry, verify_chain


def test_trajectory_tool_finds_conservative_therapy():
    result = query_patient_clinical_trajectory(
        patient_id="PAT-883910",
        therapy_keywords=["Physical Therapy"],
        lookback_months=24,
        required_duration_days=180,
    )
    assert result["total_conservative_encounters"] >= 2
    # Sample data only has 2 PT sessions ~2 weeks apart, well under 180 days.
    assert result["step_therapy_met"] is False


def test_policy_matcher_returns_known_policy():
    result = match_payer_coverage_policy_fallback(
        payer="UnitedHealthcare",
        cpt_code="27447",
        icd10_code="M17.11",
        clinical_summary="severe knee osteoarthritis, failed conservative therapy",
    )
    hits = result.get("hits", {}).get("hits", [])
    assert any(h["_source"]["policy_id"] == "POL-UHC-KNEE-01" for h in hits)


def test_drug_interaction_catches_brand_generic_mismatch():
    """The demo-killer case: Eliquis (brand for Apixaban) + Toradol
    (brand for Ketorolac) must resolve to the same interaction record as
    the generic names would."""
    result = audit_drug_drug_contraindications(
        active_rxnorm_codes=["Eliquis"],
        new_medication_code="Toradol",
    )
    hits = result.get("hits", {}).get("hits", [])
    assert len(hits) == 1
    assert hits[0]["_source"]["severity"] == "Contraindicated"


def test_resolve_medication_to_rxnorm():
    # FIXED (18 Sept): this asserted "6960", which is not Ketorolac's
    # real RxCUI anywhere in this repo -- it's an arbitrary local `code`
    # value used in data/sample/sample_fhir_encounters.json's Toradol
    # MedicationRequest fixture (a field resolve_medication_to_rxnorm
    # never reads). The actual verified RxCUI this function should
    # return is drug_b_rxnorm from the fda-drug-interactions record
    # (INT-2 in data/sample/sample_drug_interactions.json): "35827".
    assert resolve_medication_to_rxnorm("Toradol") == "35827"
    assert resolve_medication_to_rxnorm("Ketorolac") == "35827"


def test_audit_ledger_detects_tampering():
    claim_id = "CLM-TEST-TAMPER"
    append_entry(claim_id, "ADJ-TEST-1", {"decision": "APPROVED"})
    append_entry(claim_id, "ADJ-TEST-2", {"decision": "REVIEWED"})
    append_entry(claim_id, "ADJ-TEST-3", {"decision": "FINALIZED"})
    assert verify_chain(claim_id) is True

    # Tamper with the middle entry directly in the index.
    from app.es_client import get_es_client
    es = get_es_client()
    es.indices.refresh(index="audit-ledger")
    result = es.search(
        index="audit-ledger",
        query={"term": {"claim_id": claim_id}},
        sort=[{"sequence_number": "asc"}],
        size=10,
    )
    middle_doc_id = result["hits"]["hits"][1]["_id"]
    es.update(index="audit-ledger", id=middle_doc_id, doc={"record_hash": "TAMPERED"})
    es.indices.refresh(index="audit-ledger")

    assert verify_chain(claim_id) is False
