"""
Automatic claim processing: DRAFT claim with uploaded documents -> OCR ->
claim draft -> codes saved on the claim -> PENDING (ready to adjudicate).

This stands in for ARCHITECTURE.md stages 2-5 without the human coder
step (Coder Review UI isn't built; the team chose to auto-submit for
now). To keep that honest, the ledger event written by
persist_claim_draft() carries confirmed_by="auto:mediaudit-x" rather than a
coder id, and every code still cites the text it came from (a document
span, or the hospital form):

  1. OCR every document still at ocr_status=PENDING (app.pipeline.ocr).
     The hospital's form details are added as a second, separately-cited
     source (claim_draft_tool.with_form_evidence, doc_id "hospital-form").
  2. Draft: app.tools.claim_draft_tool.build_claim_draft (local
     regex/dictionary candidates + LLM pick + ranker). If the LLM is
     unavailable or fails, a deterministic draft is built from the local
     candidates alone (dictionary-verified codes, top score per code
     system), labelled origin="deterministic".
  3. Only if both a CPT and an ICD-10 code were found is the draft
     persisted (status -> PENDING), which also builds the structured
     FHIR R4 Claim the insurer receives (app/pipeline/claim_json.py).
     Otherwise the claim goes back to DRAFT
     and ProcessingFailed says what's missing -- a claim is never
     submitted with guessed or empty codes.

Runs from two places: a background task after document upload
(routers/intake.py), and inline at the start of adjudication if the claim
is still DRAFT (routers/adjudication.py). The DRAFT -> PROCESSING
transition is a conditional update, so only one of them does the work.
"""
import logging
import re
from typing import Callable

from app.drafting.candidates import gather_local_candidates
from app.drafting.dictionary import load_code_dictionary
from app.drafting.ranker import _local_score
from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS
from app.pipeline.ocr import get_ocr_service
from app.tools.audit_ledger import append_event
from app.tools.claim_draft_tool import (
    build_claim_draft,
    compute_evidence_hash,
    fetch_claim,
    fetch_claim_ocr_documents,
    persist_claim_draft,
    with_form_evidence,
)

logger = logging.getLogger(__name__)

AUTO_CONFIRMED_BY = "auto:mediaudit-x"

StepFn = Callable[[str, str], None]


class ProcessingFailed(Exception):
    """User-facing reason the claim couldn't be processed (it's back in DRAFT)."""


def _set_status_if(claim_id: str, from_status: str, to_status: str) -> bool:
    """Conditional status change; True only if this call made it. Two
    callers racing on the same DRAFT claim can't both win."""
    result = get_es_client().update_by_query(
        index=ALL_CLAIMS,
        query={"term": {"claim_id": claim_id}},
        script={
            "source": (
                "if (ctx._source.status == params.from) { ctx._source.status = params.to } "
                "else { ctx.op = 'noop' }"
            ),
            "params": {"from": from_status, "to": to_status},
        },
        conflicts="proceed",
        refresh=True,
    )
    changed = result.get("updated", 0) > 0
    if changed:
        append_event(claim_id, "STATUS_CHANGED", {"from": from_status, "to": to_status, "reason": "auto_processing"})
    return changed


def _best_candidate(candidates: list[dict], code_system: str) -> dict | None:
    by_code: dict[str, list[dict]] = {}
    for cand in candidates:
        if cand["code_system"] == code_system and cand.get("context") != "negated":
            by_code.setdefault(cand["code"], []).append(cand)
    ranked = sorted(by_code.items(), key=lambda kv: _local_score(kv[1]), reverse=True)
    if not ranked:
        return None
    code, spans = ranked[0]
    span = max(spans, key=lambda s: s["score"])
    return {
        "code": code,
        "description": span["display"],
        "cited_text": span["text"],
        "doc_id": span["doc_id"],
        "page_number": span["page_number"],
        "score": round(_local_score(spans), 3),
        "sources": ["local_dictionary"],
        "alternatives": [
            {"code": c, "description": s[0]["display"], "score": round(_local_score(s), 3)}
            for c, s in ranked[1:4]
        ],
    }


_PAYER_RE = re.compile(
    r"(?:insurance\s*(?:company|provider|carrier|plan)?|payer|insurer|health\s*plan)"
    r"\s*[:=\-–]\s*(.+)",
    re.IGNORECASE,
)
_PATIENT_ID_RE = re.compile(
    r"(?:patient\s*(?:id|ID|#|no\.?|number)|MRN|member\s*(?:id|ID|#|no\.?|number))"
    r"\s*[:=\-–]\s*([A-Za-z0-9\-]+)",
    re.IGNORECASE,
)


def _extract_field_by_regex(text: str, pattern: re.Pattern) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def deterministic_draft(claim_id: str, doc) -> dict:
    """No-LLM draft: top dictionary-verified candidate per code system,
    cited to the span it was found in. Same shape as build_claim_draft()."""
    candidates = gather_local_candidates(doc, load_code_dictionary())
    procedure = _best_candidate(candidates, "CPT")
    diagnosis = _best_candidate(candidates, "ICD10CM")
    full_text = doc.full_text
    return {
        "claim_id": claim_id,
        "status": "DRAFT",
        "origin": "deterministic",
        "cpt_code": procedure["code"] if procedure else None,
        "icd10_code": diagnosis["code"] if diagnosis else None,
        "claim_amount": None,
        "payer_name": _extract_field_by_regex(full_text, _PAYER_RE),
        "patient_id": _extract_field_by_regex(full_text, _PATIENT_ID_RE),
        "extracted_diagnoses": [diagnosis] if diagnosis else [],
        "extracted_procedures": [procedure] if procedure else [],
        "extracted_medications": [],
        "evidence_hash": compute_evidence_hash(doc),
        "source_doc_id": doc.doc_id,
        "validation_warnings": ["Drafted without the LLM (deterministic fallback): no medications extracted."],
    }


def process_claim(claim_id: str, on_step: StepFn | None = None) -> dict:
    """DRAFT -> PROCESSING -> PENDING. Returns the persist result. Raises
    ProcessingFailed (claim restored to DRAFT) if it can't be completed."""
    step = on_step or (lambda name, detail: None)

    claim = fetch_claim(claim_id)
    if claim.get("status") != "DRAFT":
        raise ProcessingFailed(f"Claim is {claim.get('status')}, not DRAFT; nothing to process.")
    if not claim.get("attached_documents"):
        raise ProcessingFailed(
            "Claim has no uploaded documents, so no codes can be extracted. "
            "Upload the clinical documents to this claim first."
        )
    if not _set_status_if(claim_id, "DRAFT", "PROCESSING"):
        raise ProcessingFailed("Claim is already being processed.")
    step("processing_started", f"Processing {len(claim['attached_documents'])} document(s) for claim {claim_id}")

    try:
        ocr_results = get_ocr_service().process_claim(claim_id)
        for r in ocr_results:
            step("ocr", f"OCR {r['doc_id']}: {r['ocr_status']} ({r.get('page_count', 0)} page(s), {r.get('ocr_engine', r.get('error', ''))})")

        try:
            doc = fetch_claim_ocr_documents(claim_id)
        except ValueError as exc:
            raise ProcessingFailed("OCR produced no pages for this claim's documents.") from exc
        doc_has_text = bool(doc.full_text.strip())
        doc = with_form_evidence(claim, doc)
        if not doc.full_text.strip():
            raise ProcessingFailed("OCR found no readable text in the uploaded documents, and the form has no clinical details.")
        step("sources", "Sources: " + ", ".join(sorted({b.doc_id for b in doc.blocks if b.text.strip()}))
             + ("" if doc_has_text else " (documents had no readable text; form details only)"))

        try:
            draft = build_claim_draft(claim_id, doc)
            draft["origin"] = "llm"
            step("draft", "Claim drafted by the LLM from the documents and form details (codes ranked against the local dictionary).")
        except Exception as exc:  # noqa: BLE001 - LLM unconfigured/unavailable: fall back, don't fail
            logger.warning("LLM draft failed for %s (%s) -- using deterministic draft", claim_id, exc)
            step("draft_fallback", f"LLM draft unavailable ({exc}); using dictionary-only extraction.")
            draft = deterministic_draft(claim_id, doc)

        missing = [label for key, label in (("cpt_code", "CPT procedure code"), ("icd10_code", "ICD-10 diagnosis code"))
                   if not draft.get(key)]
        if missing:
            raise ProcessingFailed(
                f"Could not find a {' or '.join(missing)} in the uploaded documents. "
                "Upload documents that state the diagnosis and procedure."
            )
        step("draft_codes", f"Extracted CPT {draft['cpt_code']} / ICD-10 {draft['icd10_code']} "
                            f"({len(draft['extracted_medications'])} medication(s))")

        result = persist_claim_draft(draft, confirmed_by=AUTO_CONFIRMED_BY)
        step("claim_submitted", f"Structured claim (FHIR Claim) built and submitted to the insurer (status {result['status']}).")
        return result
    except Exception as exc:
        # Anything after PROCESSING: put the claim back so it can be retried.
        _set_status_if(claim_id, "PROCESSING", "DRAFT")
        if isinstance(exc, ProcessingFailed):
            raise
        logger.exception("Processing failed for claim %s", claim_id)
        raise ProcessingFailed(f"Processing failed: {exc}") from exc


def process_claim_in_background(claim_id: str) -> None:
    """For FastAPI BackgroundTasks: never raises, just logs."""
    try:
        result = process_claim(claim_id)
        logger.info("Auto-processed claim %s -> %s", claim_id, result["status"])
    except ProcessingFailed as exc:
        logger.warning("Auto-processing claim %s stopped: %s", claim_id, exc)
    except Exception:  # noqa: BLE001
        logger.exception("Auto-processing claim %s crashed", claim_id)
