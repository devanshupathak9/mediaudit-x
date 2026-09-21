"""
OCR evidence -> in-memory claim draft, for coder review before anything is
persisted.

Pipeline stage this covers (per ARCHITECTURE.md's Ingestion -> OCR ->
Claim Draft Generation -> Coder Review flow):

  1. The claim already exists -- created at upload/intake time (DRAFT, in
     `claim-files`) or manually (PENDING, in `insurance-claims`); its
     cpt_code/icd10_code/claim_amount are null until this stage fills them
     in (see INGESTION.md's claim-files contract). We do NOT create claims
     and we do NOT ingest anything here -- fetch_claim() reads whichever
     index the claim actually lives in via ALL_CLAIMS.
  2. We retrieve the OCR'd text of the claim's attached documents
     (fetch_claim_ocr_documents, reading `document-pages` -- the exact
     index/field names INGESTION.md section 6 specifies for the
     not-yet-merged OCR stage to write. Matching that contract now means
     this module needs zero changes once OCR actually lands).
  3. We map those two retrieved things into an in-memory claim draft, per
     ARCHITECTURE.md Stage 3 -- but hybrid, not pure-LLM and not
     pure-dictionary:
       - `app/drafting/candidates.py` runs a deterministic regex + local
         code-dictionary phrase pass over the OCR text (see
         data/codes/code_dictionary.json -- a small, licensing-safe,
         curated subset covering the demo/sample data, not the full
         CMS/AMA code sets). This is the safety net against OCR corruption
         (OCR.md found Tesseract silently misreads "0" as "@" on some
         fonts) and against LLM hallucination.
       - The LLM reads the OCR text AND that local candidate list, and may
         either pick a local candidate, or -- if it's confident from its
         own knowledge of official CPT/ICD-10-CM standards, or after
         verifying with the web_search tool -- propose a code that isn't
         in the local list. Every pick still cites an exact OCR text span.
       - `app/drafting/ranker.py` then scores every code in play (local
         evidence strength + whether the LLM picked it + whether
         web_search verified it + any learned correction from past coder
         rejections, see feedback.py) and the top-ranked code is what
         actually gets attached -- not just whatever the LLM said first.
         Runner-up candidates are kept as `alternatives` for the coder.
     Medications are extracted the same way (LLM cites a span) and
     best-effort resolved to RxNorm via resolve_medication_to_rxnorm()
     (already used by adjudication) -- not run through the ranker.
  4. build_claim_draft() returns that draft as a plain dict -- nothing is
     written to Elasticsearch. It's meant to be shown to a coder for
     accept/edit/reject (the Coder Review UI, not built yet).
  5. Only once a human confirms should persist_claim_draft() be called,
     which fills in the claim's cpt_code/icd10_code/claim_amount (the
     "construct the object like sample_claims" step), sets status to
     PENDING (ARCHITECTURE.md's "Final Claim (PENDING) -- draft + coder
     changes saved"), and merges the cited extraction onto the existing
     claim document -- in whichever index it actually lives in -- and
     writes an audit-ledger event. That's the only function in this
     module that writes to Elasticsearch.

Run standalone with:
    python -m app.tools.claim_draft_tool --claim-id CLM-XXXXXXXX [--persist]
    python -m app.tools.claim_draft_tool --claim-id CLM-XXXXXXXX \\
        --ocr-json document_ocr.json [--persist]

Omit --ocr-json to pull evidence for real from `document-pages` via
fetch_claim_ocr_documents(); pass it to test against a local OCR export
instead (e.g. before that index has real data in it for a given claim).
--ocr-json shape: {"doc_id": "...", "blocks": [{"text": "...", "page_number": 1, "bounding_box": {...}}, ...]}
"""
import argparse
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.drafting.candidates import gather_local_candidates
from app.drafting.dictionary import load_code_dictionary, load_learned_corrections
from app.drafting.feedback import record_rejection
from app.drafting.ranker import rank_field
from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS
from app.llm_client import make_llm_client
from app.pipeline.claim_json import build_fhir_claim
from app.tools.audit_ledger import append_event
from app.tools.drug_interaction_tool import resolve_medication_to_rxnorm

logger = logging.getLogger(__name__)

# Contract from INGESTION.md section 6 ("Building OCR on top"). The OCR
# stage that writes this index hasn't merged yet -- matching its exact
# field names here means nothing in this module has to change once it
# does. page_id ({doc_id}:p{n}), doc_id, claim_id, page_number, text,
# engine, ocr_confidence, char_count.
DOCUMENT_PAGES_INDEX = "document-pages"

# Anthropic's server-side web search tool -- lets the LLM verify an exact
# CPT/ICD-10-CM code against a public source instead of guessing. Not
# guaranteed to be supported by every provider/model on Bedrock yet;
# call_llm_for_extraction() falls back to a plain forced-tool call (no
# search, trained knowledge only) if the API rejects it.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

MAX_EXTRACTION_ROUNDS = 4

EXTRACTION_TOOL = {
    "name": "submit_claim_extraction",
    "description": (
        "Submit the structured draft claim extracted from the clinical "
        "documentation. A CANDIDATES list (verified against our local code "
        "dictionary) is provided -- prefer a candidate when it matches the "
        "documentation. You may still propose a code that isn't in "
        "CANDIDATES if you are confident of it from your own knowledge of "
        "official CPT/ICD-10-CM standards, or after verifying it with the "
        "web_search tool -- set source accordingly. Never guess a code you "
        "are not confident is correct. cited_text must be an exact "
        "verbatim substring of the document text you were given, and "
        "doc_id must match the [doc ... page ...] tag the citation came from."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "diagnoses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Official ICD-10-CM code, e.g. M17.11"},
                        "description": {"type": "string"},
                        "cited_text": {"type": "string"},
                        "doc_id": {"type": "string"},
                        "page_number": {"type": "integer"},
                        "source": {
                            "type": "string",
                            "enum": ["local_dictionary", "llm_knowledge", "web_search"],
                            "description": "local_dictionary if this code came from CANDIDATES, llm_knowledge if from your own training, web_search if you verified it via the tool",
                        },
                    },
                    "required": ["code", "description", "cited_text", "doc_id", "page_number", "source"],
                },
            },
            "procedures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Official CPT/HCPCS code, e.g. 27447"},
                        "description": {"type": "string"},
                        "cited_text": {"type": "string"},
                        "doc_id": {"type": "string"},
                        "page_number": {"type": "integer"},
                        "source": {
                            "type": "string",
                            "enum": ["local_dictionary", "llm_knowledge", "web_search"],
                            "description": "local_dictionary if this code came from CANDIDATES, llm_knowledge if from your own training, web_search if you verified it via the tool",
                        },
                    },
                    "required": ["code", "description", "cited_text", "doc_id", "page_number", "source"],
                },
            },
            "medications": {
                "type": "array",
                "description": "Every medication mentioned as newly prescribed or currently active for this patient. Empty list if none mentioned.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "cited_text": {"type": "string"},
                        "doc_id": {"type": "string"},
                        "page_number": {"type": "integer"},
                    },
                    "required": ["name", "cited_text", "doc_id", "page_number"],
                },
            },
            "total_billed_amount": {"type": "number"},
            "payer_name": {
                "type": "string",
                "description": (
                    "Insurance company / payer name as stated in the documents "
                    "or form (e.g. 'UnitedHealthcare', 'Aetna', 'Medicare'). "
                    "Return the name exactly as written. Empty string if not mentioned."
                ),
            },
            "patient_id": {
                "type": "string",
                "description": (
                    "Patient ID / MRN / member number as stated in the documents "
                    "or form. Return it exactly as written. Empty string if not found."
                ),
            },
        },
        "required": ["diagnoses", "procedures", "medications", "total_billed_amount"],
    },
}


@dataclass
class OcrBlock:
    text: str
    page_number: int
    bounding_box: dict | None = None
    # Which of the claim's (possibly several) uploaded documents this block
    # came from -- e.g. one of 5 attached PDFs. page_number alone is
    # ambiguous once a claim has more than one document; this disambiguates
    # citations. Falls back to the OcrDocument's own doc_id for the
    # single-file CLI case where blocks don't carry their own.
    doc_id: str | None = None


@dataclass
class OcrDocument:
    doc_id: str
    blocks: list = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


FORM_DOC_ID = "hospital-form"
FORM_PAGE_NUMBER = 1

_FORM_FIELDS = [
    ("clinical", "chief_complaint", "Chief complaint"),
    ("clinical", "problem_description", "Problem description"),
    ("clinical", "symptoms", "Symptoms"),
    ("clinical", "duration", "Duration"),
    ("clinical", "diagnosis_in_words", "Diagnosis"),
    ("clinical", "procedures", "Procedures performed"),
    ("clinical", "treatment", "Treatment"),
    ("clinical", "medications", "Medications"),
    ("admission", "admission_date", "Admission date"),
    ("admission", "discharge_date", "Discharge date"),
    ("services", "services_provided", "Services provided"),
    ("hospital", "department", "Department"),
    ("insurance", "company", "Insurance company"),
    ("insurance", "policy_number", "Policy number"),
]


def form_evidence_block(claim: dict) -> OcrBlock | None:
    details = claim.get("details") or {}
    lines = []
    for section, key, label in _FORM_FIELDS:
        value = (details.get(section) or {}).get(key)
        if value:
            lines.append(f"{label}: {value}")
    if details.get("estimated_total_cost"):
        lines.append(f"Estimated total cost: {details['estimated_total_cost']}")
    if not lines:
        return None
    return OcrBlock(text="\n".join(lines), page_number=FORM_PAGE_NUMBER, doc_id=FORM_DOC_ID)


def with_form_evidence(claim: dict, doc: OcrDocument) -> OcrDocument:
    """The OCR'd documents plus the hospital form block (if the form has
    any clinical details). Returns a new OcrDocument; `doc` is untouched."""
    block = form_evidence_block(claim)
    if block is None or any(b.doc_id == FORM_DOC_ID for b in doc.blocks):
        return doc
    return OcrDocument(doc_id=doc.doc_id, blocks=[*doc.blocks, block])


# --------------------------------------------------------------------------
# Retrieval -- claim metadata (claim-files or insurance-claims, via
# ALL_CLAIMS) and OCR evidence (document-pages).
# --------------------------------------------------------------------------

def _find_claim_hit(es, claim_id: str) -> dict:
    result = es.search(
        index=ALL_CLAIMS,
        query={"term": {"claim_id": claim_id}},
        size=1,
        ignore_unavailable=True,
    )
    hits = result["hits"]["hits"]
    if not hits:
        logger.error("Claim %s not found in %s", claim_id, ALL_CLAIMS)
        raise ValueError(
            f"Claim {claim_id} not found in {ALL_CLAIMS}. A draft can only be "
            "built for a claim that already exists (created via intake upload "
            "or POST /claims) -- this module never creates claims."
        )
    return hits[0]


def fetch_claim(claim_id: str) -> dict:
    """Retrieves the already-created claim record (payer_name, patient_id,
    and whatever cpt_code/icd10_code/claim_amount was already set -- null
    for an upload-created claim, see INGESTION.md)."""
    es = get_es_client()
    logger.info("Fetching claim %s from %s", claim_id, ALL_CLAIMS)
    hit = _find_claim_hit(es, claim_id)
    claim = hit["_source"]
    logger.debug("Claim %s (index=%s): payer=%s cpt=%s icd10=%s attached_documents=%d",
                 claim_id, hit["_index"], claim.get("payer_name"), claim.get("cpt_code"),
                 claim.get("icd10_code"), len(claim.get("attached_documents", [])))
    return claim


def fetch_claim_ocr_documents(claim_id: str) -> OcrDocument:
    """Retrieves every OCR'd page for this claim's attached documents from
    `document-pages` (see INGESTION.md section 6) and merges them into one
    OcrDocument spanning however many files were uploaded for this claim."""
    es = get_es_client()
    logger.info("Fetching OCR evidence for claim %s from %s", claim_id, DOCUMENT_PAGES_INDEX)
    result = es.search(
        index=DOCUMENT_PAGES_INDEX,
        query={"term": {"claim_id": claim_id}},
        sort=[{"doc_id": "asc"}, {"page_number": "asc"}],
        size=1000,
        ignore_unavailable=True,
    )
    hits = result["hits"]["hits"]
    if not hits:
        logger.warning("No OCR pages found in %s for claim %s", DOCUMENT_PAGES_INDEX, claim_id)
        raise ValueError(
            f"No OCR evidence found in {DOCUMENT_PAGES_INDEX} for claim {claim_id} -- "
            "has OCR run on this claim's uploaded documents yet?"
        )

    blocks = [
        OcrBlock(
            text=h["_source"].get("text", ""),
            page_number=h["_source"].get("page_number", 0),
            doc_id=h["_source"].get("doc_id"),
        )
        for h in hits
    ]
    doc_ids = sorted({b.doc_id for b in blocks if b.doc_id})
    logger.info("Fetched %d OCR page(s) across %d document(s) for claim %s: %s",
                len(blocks), len(doc_ids), claim_id, doc_ids)
    return OcrDocument(doc_id=f"{claim_id}-evidence-bundle", blocks=blocks)


# --------------------------------------------------------------------------
# LLM extraction -- hybrid: the model sees the local (deterministic)
# candidate list AND the raw OCR text, and may pick from either, with
# web_search available to verify a code that isn't in the local list. The
# ranker (see build_claim_draft) has the final say on which code actually
# gets attached, not the LLM's raw output.
# --------------------------------------------------------------------------

def _format_candidates_block(local_candidates: list[dict]) -> str:
    seen: dict[tuple, dict] = {}
    for c in local_candidates:
        key = (c["code_system"], c["code"])
        seen.setdefault(key, c)
    if not seen:
        return "(none found by the local regex/dictionary pass)"
    return "\n".join(
        f"- [{cs}] {code} — {c['display']} (found via {c['method']}, page {c['page_number']})"
        for (cs, code), c in seen.items()
    )


def _build_extraction_prompt(doc: OcrDocument, local_candidates: list[dict]) -> str:
    pages = "\n\n".join(f"[doc {b.doc_id or doc.doc_id} page {b.page_number}] {b.text}" for b in doc.blocks)
    candidates_block = _format_candidates_block(local_candidates)
    has_form = any(b.doc_id == FORM_DOC_ID for b in doc.blocks)
    form_note = f"""
The block tagged [doc {FORM_DOC_ID} page {FORM_PAGE_NUMBER}] is not a clinical
document: it is what the hospital typed on the claim form. Use it to
understand what was done and billed, but when the same fact appears in a
clinical document, cite the document instead of the form. Cite the form
only for facts no document states.""" if has_form else ""
    return f"""You are a certified medical coder assistant. Read the clinical
documentation below and identify every diagnosis and procedure it
documents, assigning each the correct official ICD-10-CM or CPT/HCPCS
code. A CANDIDATES list, already verified against our local code
dictionary, is provided below -- prefer one of these when it matches the
documentation (set source: local_dictionary). If the documentation
clearly supports a code that isn't in CANDIDATES, you may still propose
it from your own knowledge of these public coding standards
(source: llm_knowledge), or verify it with the web_search tool first
(source: web_search) -- do not guess. For every selected
diagnosis/procedure, cite the EXACT text span from the document that
supports it, and the doc_id and page it appears on from that span's
[doc ... page ...] tag -- cited_text must be a verbatim substring of the
document text below, not a paraphrase.
Separately, list every medication mentioned as newly prescribed or
currently active for this patient, with the same citation rules. If none
are mentioned, return an empty medications list.
If a total billed amount is not stated in the document, use 0.
Also extract the insurance company / payer name and the patient ID / MRN
if they appear anywhere in the documents or form. Return them exactly as
written; leave as empty string if not found.{form_note}

CANDIDATES:
{candidates_block}

DOCUMENT TEXT (OCR, by page):
{pages}

Call submit_claim_extraction with the result."""


def call_llm_for_extraction(doc: OcrDocument, local_candidates: list[dict]) -> dict:
    client, model_id = make_llm_client()
    if client is None:
        raise RuntimeError(
            "No LLM credentials configured (LLM_PROVIDER + Bedrock/Anthropic "
            "settings in .env) -- same requirement as app/agent/orchestrator.py."
        )

    prompt = _build_extraction_prompt(doc, local_candidates)
    use_web_search = True
    messages = [{"role": "user", "content": prompt}]

    for round_num in range(MAX_EXTRACTION_ROUNDS):
        tools = [WEB_SEARCH_TOOL, EXTRACTION_TOOL] if use_web_search else [EXTRACTION_TOOL]
        tool_choice = {"type": "auto"} if use_web_search else {"type": "tool", "name": "submit_claim_extraction"}
        logger.info("Calling LLM (%s) for extraction, round %d (web_search=%s)", model_id, round_num, use_web_search)
        try:
            response = client.messages.create(
                model=model_id,
                max_tokens=4096,
                tools=tools,
                tool_choice=tool_choice,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 - provider/model may not support web_search yet
            if use_web_search:
                logger.warning("LLM call with web_search tool failed (%s) -- retrying without it", exc)
                use_web_search = False
                messages = [{"role": "user", "content": prompt}]
                continue
            raise

        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_claim_extraction":
                payload = dict(block.input)
                logger.info(
                    "LLM extraction returned %d diagnosis(es), %d procedure(s), %d medication(s) (web_search=%s)",
                    len(payload.get("diagnoses", [])), len(payload.get("procedures", [])),
                    len(payload.get("medications", [])), use_web_search,
                )
                return payload

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": "Call submit_claim_extraction now with your findings."})

    logger.error("LLM did not return a submit_claim_extraction tool call after %d round(s)", MAX_EXTRACTION_ROUNDS)
    raise RuntimeError("Claude did not return a submit_claim_extraction tool call")


def validate_extraction(payload: dict, doc: OcrDocument) -> list:
    """Flags, never silently drops: anything suspicious is surfaced to the
    human coder rather than hidden. No candidate-list check anymore (there
    is no local dictionary to check against) -- just citation integrity."""
    warnings = []
    full_text = doc.full_text

    for section in ("diagnoses", "procedures", "medications"):
        for item in payload.get(section, []):
            cited = item.get("cited_text", "")
            label = item.get("code") or item.get("name")
            if cited and cited not in full_text:
                warnings.append(f"{section}: cited_text for {label} not found verbatim in the source OCR text")

    if not payload.get("diagnoses") and not payload.get("procedures") and not payload.get("medications"):
        warnings.append("No diagnoses, procedures, or medications extracted -- route to manual review")

    for w in warnings:
        logger.warning(w)
    return warnings


def _cross_check_against_submitted_claim(claim: dict, llm_payload: dict) -> list[str]:
    """If the claim already had a cpt_code/icd10_code set (e.g. re-running
    extraction, or a manually-created claim), flags a mismatch against what
    the evidence documents actually support."""
    warnings = []
    extracted_procedure_codes = {p.get("code") for p in llm_payload.get("procedures", [])}
    extracted_diagnosis_codes = {d.get("code") for d in llm_payload.get("diagnoses", [])}

    submitted_cpt = claim.get("cpt_code")
    if submitted_cpt and extracted_procedure_codes and submitted_cpt not in extracted_procedure_codes:
        warnings.append(
            f"Submitted cpt_code {submitted_cpt} is not among the codes the evidence "
            f"documents support ({sorted(extracted_procedure_codes)}) -- review before confirming."
        )
    submitted_icd10 = claim.get("icd10_code")
    if submitted_icd10 and extracted_diagnosis_codes and submitted_icd10 not in extracted_diagnosis_codes:
        warnings.append(
            f"Submitted icd10_code {submitted_icd10} is not among the codes the evidence "
            f"documents support ({sorted(extracted_diagnosis_codes)}) -- review before confirming."
        )
    for w in warnings:
        logger.warning(w)
    return warnings


# --------------------------------------------------------------------------
# Draft build (in-memory only) + explicit persist step
# --------------------------------------------------------------------------

def compute_evidence_hash(doc: OcrDocument) -> str:
    return hashlib.sha256(doc.full_text.encode("utf-8")).hexdigest()


def _rank_items(items: list[dict], code_system: str, local_candidates: list[dict],
                 learned_corrections: list[dict]) -> list[dict]:
    """Ranks each LLM-picked item against local candidates on the same
    page (see ranker.rank_field) -- the top rank may override the LLM's
    raw pick if local evidence or a learned correction outranks it."""
    ranked_items = []
    for item in items:
        same_page = [
            c for c in local_candidates
            if c["doc_id"] == item.get("doc_id") and c["page_number"] == item.get("page_number")
        ]
        ranked_items.append(rank_field(item, code_system, same_page, learned_corrections))
    return ranked_items


def build_claim_draft(claim_id: str, doc: OcrDocument) -> dict:
    """
    Retrieves the existing claim (fetch_claim) and maps the given OCR
    evidence onto it: local candidate generation (regex + code dictionary)
    -> LLM extraction (candidates + own knowledge + optional web_search)
    -> ranking (local evidence + LLM pick + learned corrections) ->
    in-memory draft, including the flat cpt_code/icd10_code/claim_amount
    this claim doesn't have yet (see INGESTION.md). Writes nothing to
    Elasticsearch -- the caller shows this to a coder and decides whether
    to call persist_claim_draft().
    """
    logger.info("Building draft for claim %s from %d OCR block(s) (doc bundle %s)",
                claim_id, len(doc.blocks), doc.doc_id)
    claim = fetch_claim(claim_id)
    doc = with_form_evidence(claim, doc)

    code_dictionary = load_code_dictionary()
    local_candidates = gather_local_candidates(doc, code_dictionary)
    learned_corrections = load_learned_corrections()

    llm_payload = call_llm_for_extraction(doc, local_candidates)
    warnings = validate_extraction(llm_payload, doc)

    diagnoses = _rank_items(llm_payload.get("diagnoses", []), "ICD10CM", local_candidates, learned_corrections)
    procedures = _rank_items(llm_payload.get("procedures", []), "CPT", local_candidates, learned_corrections)
    warnings.extend(_cross_check_against_submitted_claim(claim, {"diagnoses": diagnoses, "procedures": procedures}))

    medications = llm_payload.get("medications", [])
    for item in medications:
        item["rxnorm_code"] = resolve_medication_to_rxnorm(item.get("name", ""))
        if not item["rxnorm_code"]:
            logger.debug("No RxNorm resolution for medication %r", item.get("name"))

    draft = {
        "claim_id": claim_id,
        "status": "DRAFT" if not warnings else "DRAFT_NEEDS_REVIEW",
        # The fields claim-files/insurance-claims don't have yet -- this
        # stage is what constructs the rest of the object, same shape as
        # data/sample/sample_claims.json. Top-ranked code per field, per
        # the ranker -- not necessarily the LLM's first pick.
        "cpt_code": procedures[0]["code"] if procedures else None,
        "icd10_code": diagnoses[0]["code"] if diagnoses else None,
        "claim_amount": llm_payload.get("total_billed_amount") or None,
        "payer_name": (llm_payload.get("payer_name") or "").strip() or None,
        "patient_id": (llm_payload.get("patient_id") or "").strip() or None,
        "extracted_diagnoses": diagnoses,
        "extracted_procedures": procedures,
        "extracted_medications": medications,
        "evidence_hash": compute_evidence_hash(doc),
        "source_doc_id": doc.doc_id,
        "validation_warnings": warnings,
    }

    logger.info(
        "Draft built for %s: status=%s cpt=%s icd10=%s amount=%s (%d dx, %d px, %d meds, %d warning(s)) "
        "-- not persisted, call persist_claim_draft() after review",
        claim_id, draft["status"], draft["cpt_code"], draft["icd10_code"], draft["claim_amount"],
        len(diagnoses), len(procedures), len(medications), len(warnings),
    )
    return draft


def persist_claim_draft(draft: dict, coder_corrections: list[dict] | None = None,
                        confirmed_by: str = "coder") -> dict:
    """
    Call only after a coder has reviewed/confirmed the draft from
    build_claim_draft() (possibly with edits applied to it first). Fills in
    the claim's cpt_code/icd10_code/claim_amount (null until now, per
    INGESTION.md) and merges the cited extraction onto whichever index the
    claim actually lives in (claim-files or insurance-claims), then writes
    an audit-ledger event. This is the only function in this module that
    writes to Elasticsearch.

    coder_corrections (optional): the ranker's feedback loop. One entry
    per field the coder rejected and re-picked, e.g.
    {"field_type": "CPT", "rejected_code": "27130", "corrected_code":
    "27447", "cited_text": "..."}. Each is recorded via
    drafting.feedback.record_rejection() so future rankings for similar
    text favor the coder's correction. Stands in for the full
    review-actions audit trail (ARCHITECTURE.md Stage 4), not built yet --
    the caller currently has to know what was rejected.
    """
    es = get_es_client()
    claim_id = draft["claim_id"]
    logger.info("Persisting confirmed draft for claim %s (status=%s)", claim_id, draft["status"])

    for correction in (coder_corrections or []):
        record_rejection(
            claim_id=claim_id,
            field_type=correction["field_type"],
            rejected_code=correction["rejected_code"],
            corrected_code=correction["corrected_code"],
            cited_text=correction.get("cited_text", ""),
        )

    hit = _find_claim_hit(es, claim_id)
    index_name = hit["_index"]

    updated = {
        **hit["_source"],
        "extracted_diagnoses": draft["extracted_diagnoses"],
        "extracted_procedures": draft["extracted_procedures"],
        "extracted_medications": draft["extracted_medications"],
        "evidence_hash": draft["evidence_hash"],
        "source_doc_id": draft["source_doc_id"],
        "validation_warnings": draft["validation_warnings"],
        # The draft's own DRAFT/DRAFT_NEEDS_REVIEW status is only for the
        # coder-review UI (see build_claim_draft) -- persist_claim_draft is
        # only ever called once a coder has actually confirmed it, so the
        # claim becomes PENDING here regardless, per ARCHITECTURE.md's
        # "Final Claim (PENDING) -- draft + coder changes saved" stage.
        "status": "PENDING",
    }
    # Fill in, don't blank out: only overwrite if we actually extracted
    # something, so re-running with a weaker OCR pass can't null a
    # previously-good value.
    if draft.get("cpt_code"):
        updated["cpt_code"] = draft["cpt_code"]
    if draft.get("icd10_code"):
        updated["icd10_code"] = draft["icd10_code"]
    if draft.get("claim_amount"):
        updated["claim_amount"] = draft["claim_amount"]
    if not updated.get("payer_name"):
        details = updated.get("details") or {}
        updated["payer_name"] = (
            draft.get("payer_name")
            or (details.get("insurance") or {}).get("company")
            or None
        )
    if not updated.get("patient_id"):
        updated["patient_id"] = draft.get("patient_id") or None

    updated["fhir_claim"] = build_fhir_claim(updated)
    fhir_claim_sha256 = hashlib.sha256(
        json.dumps(updated["fhir_claim"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    es.index(index=index_name, id=hit["_id"], document=updated)
    es.indices.refresh(index=index_name)

    ledger_entry = append_event(
        claim_id=claim_id,
        event_type="CLAIM_DRAFT_CONFIRMED",
        payload={
            "confirmed_by": confirmed_by,
            "origin": draft.get("origin"),
            "evidence_hash": draft["evidence_hash"],
            "cpt_code": updated.get("cpt_code"),
            "icd10_code": updated.get("icd10_code"),
            "claim_amount": updated.get("claim_amount"),
            "extracted_diagnoses": draft["extracted_diagnoses"],
            "extracted_procedures": draft["extracted_procedures"],
            "extracted_medications": draft["extracted_medications"],
            "fhir_claim_sha256": fhir_claim_sha256,
        },
        ref_id=draft["source_doc_id"],
    )
    logger.info("Persisted %s status=%s -> %s (audit-ledger seq %d)",
                claim_id, updated["status"], index_name, ledger_entry["sequence_number"])
    return {"claim_id": claim_id, "status": updated["status"], "index": index_name, "ledger_entry": ledger_entry}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load_ocr_document(path: Path) -> OcrDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    top_level_doc_id = raw.get("doc_id", path.stem)
    blocks = [
        OcrBlock(
            text=b.get("text", ""),
            page_number=b.get("page_number", 0),
            bounding_box=b.get("bounding_box"),
            doc_id=b.get("doc_id", top_level_doc_id),
        )
        for b in raw.get("blocks", [])
    ]
    if not blocks:
        raise ValueError(f"No OCR blocks found in {path}")
    return OcrDocument(doc_id=top_level_doc_id, blocks=blocks)


if __name__ == "__main__":
    from app.logging_config import configure_logging
    configure_logging()

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claim-id", required=True, help="An existing claim_id (already created via intake upload or POST /claims)")
    ap.add_argument("--ocr-json", type=Path, help="Local OCR export -- stand-in until document-pages has real data for this claim")
    ap.add_argument("--persist", action="store_true", help="Also merge the draft onto the claim + write the audit-ledger event (skips the review step -- for testing only)")
    ap.add_argument("--reject", action="append", default=[], metavar="FIELD_TYPE:REJECTED:CORRECTED",
                     help="Simulate a coder rejection to test the ranker feedback loop, e.g. --reject CPT:27130:27447 "
                          "(implies --persist). Repeatable.")
    args = ap.parse_args()

    document = _load_ocr_document(args.ocr_json) if args.ocr_json else fetch_claim_ocr_documents(args.claim_id)
    result = build_claim_draft(args.claim_id, document)
    print(json.dumps(result, indent=2))

    if args.persist or args.reject:
        corrections = []
        for spec in args.reject:
            field_type, rejected_code, corrected_code = spec.split(":")
            cited_text = next(
                (f["cited_text"] for f in (result["extracted_diagnoses"] + result["extracted_procedures"])
                 if f["code"] == rejected_code),
                "",
            )
            corrections.append({
                "field_type": field_type, "rejected_code": rejected_code,
                "corrected_code": corrected_code, "cited_text": cited_text,
            })
        persist_result = persist_claim_draft(result, coder_corrections=corrections)
        print(json.dumps(persist_result, indent=2))
