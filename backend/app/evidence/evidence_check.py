"""
Claim vs Evidence Check (ARCHITECTURE.md Stage 6) -- before any payer
logic, confirm the documents actually support the claim's final codes.
Catches a coder-added code with no supporting text, or upcoding.

Run as the first step of agent/orchestrator.adjudicate_claim() (which
emits it as a reasoning_step and persists the result), deterministic, no
LLM, using data this project already has:

  - Direct span: the claim's extracted_diagnoses/extracted_procedures
    (written by claim_draft_tool.build_claim_draft/persist_claim_draft)
    already carry {cited_text, doc_id, page_number} -- if that span still
    verifies against document-pages.text, that's SUPPORTED at full
    strength, no new search needed.
  - Search: a code with no matching extracted_* entry (e.g. hand-typed on
    a claim created via POST /claims, or coder-added/edited without a
    span) is searched for in the claim's OCR page text -- the code string
    itself, or its local-dictionary display/synonyms (the same small
    curated set app/drafting uses).
  - A claim with no attached documents at all (every seeded demo claim,
    CLM-1001.../CLM-2001...) is NOT_APPLICABLE, not a failure -- per
    ARCHITECTURE.md design principle #6, these must keep adjudicating
    exactly as they do today.

This module only reads -- it doesn't write to Elasticsearch. The caller
(orchestrator.adjudicate_claim) persists the result and the ledger event,
same pattern as every other tool function in app/tools/.
"""
import logging
from datetime import datetime, timezone

from app.drafting.dictionary import code_lookup, load_code_dictionary
from app.evidence.rules import check_laterality
from app.tools.claim_draft_tool import fetch_claim_ocr_documents

logger = logging.getLogger(__name__)

DIRECT_SPAN_STRENGTH = 1.0
SEARCH_MATCH_STRENGTH = 0.7
LATERALITY_DOWNGRADE_STRENGTH = 0.5


def _page_text(doc, doc_id: str | None, page_number: int | None) -> str | None:
    for block in doc.blocks:
        if block.doc_id == doc_id and block.page_number == page_number:
            return block.text
    return None


def _evidence_entry(doc_id: str | None, page_number: int | None, page_text: str | None, cited_text: str) -> dict:
    idx = page_text.find(cited_text) if page_text else -1
    return {
        "source_index": "document-pages",
        "source_id": f"{doc_id}:p{page_number}",
        "byte_offset_start": idx if idx != -1 else 0,
        "byte_offset_end": (idx + len(cited_text)) if idx != -1 else 0,
        "excerpt": cited_text,
    }


def _collect_codes_to_check(claim: dict) -> list[tuple[str, str, dict | None]]:
    """(code_system, code, matching extracted_* entry or None) for the
    claim's final primary codes -- these are what feed the decision."""
    entries = []
    cpt = claim.get("cpt_code")
    if cpt:
        matching = next((p for p in claim.get("extracted_procedures", []) if p.get("code") == cpt), None)
        entries.append(("CPT", cpt, matching))
    icd10 = claim.get("icd10_code")
    if icd10:
        matching = next((d for d in claim.get("extracted_diagnoses", []) if d.get("code") == icd10), None)
        entries.append(("ICD10CM", icd10, matching))
    return entries


def _check_one_code(code_system: str, code: str, extracted_entry: dict | None,
                     doc, code_dictionary: list[dict]) -> dict:
    if extracted_entry and extracted_entry.get("cited_text"):
        doc_id, page_number = extracted_entry.get("doc_id"), extracted_entry.get("page_number")
        page_text = _page_text(doc, doc_id, page_number)
        cited_text = extracted_entry["cited_text"]
        if page_text is not None and cited_text in page_text:
            result, strength = "SUPPORTED", DIRECT_SPAN_STRENGTH
            if check_laterality(code, code_dictionary, cited_text):
                result, strength = "WEAK", LATERALITY_DOWNGRADE_STRENGTH
            return {
                "code": code, "code_system": code_system, "result": result, "strength": strength,
                "evidence": [_evidence_entry(doc_id, page_number, page_text, cited_text)],
            }
        logger.warning(
            "Evidence check: cited_text for %s no longer verifies against document-pages "
            "(doc_id=%s page=%s) -- falling back to a text search", code, doc_id, page_number,
        )

    # Search fallback: no direct span, or the span didn't re-verify.
    entry = code_lookup(code_dictionary, code)
    phrases = [code, *([entry["display"], *entry.get("synonyms", [])] if entry else [])]
    for block in doc.blocks:
        lower_text = block.text.lower()
        for phrase in phrases:
            idx = lower_text.find(phrase.lower())
            if idx == -1:
                continue
            matched_text = block.text[idx: idx + len(phrase)]
            result, strength = "SUPPORTED", SEARCH_MATCH_STRENGTH
            if check_laterality(code, code_dictionary, matched_text):
                result, strength = "WEAK", LATERALITY_DOWNGRADE_STRENGTH
            return {
                "code": code, "code_system": code_system, "result": result, "strength": strength,
                "evidence": [_evidence_entry(block.doc_id, block.page_number, block.text, matched_text)],
            }

    return {"code": code, "code_system": code_system, "result": "UNSUPPORTED", "strength": 0.0, "evidence": []}


def _result(claim_id: str, overall: str, codes: list[dict]) -> dict:
    return {
        "claim_id": claim_id,
        "overall": overall,
        "codes": codes,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _overall_result(results: list[dict]) -> str:
    if not results:
        return "NOT_APPLICABLE"
    outcomes = {r["result"] for r in results}
    if "UNSUPPORTED" in outcomes:
        return "UNSUPPORTED"
    if "WEAK" in outcomes:
        return "PARTIAL"
    return "SUPPORTED"


def check_claim_evidence(claim: dict) -> dict:
    """
    Returns {claim_id, overall: SUPPORTED|PARTIAL|UNSUPPORTED|NOT_APPLICABLE,
    codes: [{code, code_system, result, strength, evidence}]}.
    """
    claim_id = claim.get("claim_id", "")

    if not claim.get("attached_documents"):
        logger.info("Claim %s has no attached documents -- evidence check NOT_APPLICABLE", claim_id)
        return _result(claim_id, "NOT_APPLICABLE", [])

    try:
        doc = fetch_claim_ocr_documents(claim_id)
    except ValueError as exc:
        logger.warning(
            "Claim %s has attached documents but no OCR evidence yet (%s) -- evidence check NOT_APPLICABLE",
            claim_id, exc,
        )
        return _result(claim_id, "NOT_APPLICABLE", [])

    code_dictionary = load_code_dictionary()
    codes_to_check = _collect_codes_to_check(claim)
    if not codes_to_check:
        return _result(claim_id, "NOT_APPLICABLE", [])

    results = [
        _check_one_code(code_system, code, extracted_entry, doc, code_dictionary)
        for code_system, code, extracted_entry in codes_to_check
    ]
    overall = _overall_result(results)
    logger.info("Evidence check for claim %s: overall=%s codes=%s",
                claim_id, overall, [(r["code"], r["result"]) for r in results])
    return _result(claim_id, overall, results)
