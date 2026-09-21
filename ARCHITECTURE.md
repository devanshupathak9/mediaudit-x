# MediAudit-X — Target Architecture (document → decision)

> **How to use this file.** This is the build spec for extending MediAudit-X
> from "adjudicate a claim someone typed in" to "hospital uploads documents →
> coded, reviewed, adjudicated, audited claim." Feed it to a coding model as
> context. Each stage has **inputs, outputs, files to create/modify, the
> Elasticsearch index it touches, what the LLM may and may not do, the
> fallback, the ledger event, and acceptance criteria.** Build in the phase
> order in §9. Rules in §10 are non-negotiable.

---

## 0. End-to-end workflow

```
Hospital uploads documents
          │
          ▼
 [1] Ingestion ─────────── store files, create claim in DRAFT status
          │
          ▼
 [2] OCR ───────────────── page text + chunks with (doc_id, page, char offsets)
          │
          ▼
 [3] Claim Draft Generation
       ├─ regex + code dictionary → candidate CPT / ICD-10
       ├─ RxNorm lookup           → candidate drugs
       └─ LLM picks from candidates; every field cites a source span
          │
          ▼
 [4] Coder Review UI ────── source text shown next to each field
       accept / edit / reject each field → sign off
          │
          ▼
 [5] Final Claim (PENDING) ─ draft + coder changes saved
          │
          ▼
 [6] Claim vs Evidence Check ─ do the documents support the final codes?
          │
          ▼
 [7] Insurance Evaluator ── policy match + patient history + drug interaction
          │                  (existing agent/orchestrator.py)
          ▼
 [8] Decision ──────────── APPROVED / DENIED / REQUEST_INFO (deterministic)
          │
          ▼
 [9] Audit Ledger ──────── every stage above, hash-chained per claim
          │
          ▼
[10] Output ────────────── letter + FHIR ClaimResponse + alert
          │
          ▼
[11] Evaluation ────────── extraction accuracy (from coder edits)
                           + decision accuracy (vs labelled cases)
```

The audit ledger (stage 9) is written **at every stage**, not only at the
end; it sits after Decision in the diagram because that is where the chain
is sealed.

---

## 1. What exists today vs. what this plan adds

| Area | Today (in repo) | This plan |
|---|---|---|
| Claim intake | `POST /claims` with codes typed by hand, status `PENDING`; `POST /claims/{id}/documents` stores files on local disk, nothing reads them (`routers/claims.py`) | Upload-first intake → claim in `DRAFT`, files hashed and registered |
| Text extraction | `pdfplumber` used only for policy PDFs (`ingestion/ingest_policies.py`) | OCR stage for claim documents: page text + offset-addressable chunks |
| Coding | None — the user enters CPT/ICD | Candidate generation (regex + dictionary + RxNorm) + constrained LLM selection with citations |
| Human review | None | Coder review UI, per-field accept/edit/reject, sign-off |
| Evidence check | None | Final codes verified against the documents' text |
| Adjudication | `agent/orchestrator.py` — Claude tool loop over 3 tools, deterministic `_decide()`, deterministic fallback sweep | Reused. Now fed by the **final claim** + **document-extracted medications**, plus evidence-check result into `_decide()` |
| Ledger | `tools/audit_ledger.py` — one entry per adjudication; payload **not** stored; `verify_chain` checks `prev_hash` linkage only | One entry per pipeline event; payload hash stored; full recompute verification |
| Output | Templated letter + minimal FHIR ClaimResponse (`actuators/letter_generator.py`); `interaction_alert` SSE event | Same, plus FHIR items/adjudication detail and a persisted alert |
| Evaluation | `eval/run_benchmark.py` skeleton, all `NotImplementedError` | Extraction metrics computed from coder review events; decision accuracy vs labelled set |

Keep the stack: **FastAPI + Elasticsearch (Serverless or local) + Claude via
AWS Bedrock (`llm_provider="bedrock"`, direct Anthropic as fallback) +
Next.js 15 / Tailwind frontend.** No new database: Elasticsearch is the
system of record, like the rest of the repo.

---

## 2. Design principles (carry these into every stage)

1. **The LLM chooses, it never invents.** In drafting, the LLM may only pick
   a `candidate_id` that stage 3a produced and cite a `span_id` that stage 2
   produced. Server-side validation rejects anything else. In adjudication,
   the LLM only picks tools; `_decide()` makes the decision.
2. **Every value points to text.** Every extracted field and every piece of
   cited evidence resolves to `(doc_id, page, char_start, char_end)` and the
   quoted text must equal `page_text[char_start:char_end]` exactly.
3. **Deterministic fallback everywhere an LLM is used.** Same pattern as
   `_deterministic_tool_sweep`: if the LLM is unconfigured or fails, the
   pipeline still completes (lower quality, clearly labelled `origin:
   "deterministic"`).
4. **Humans own the codes.** Nothing reaches adjudication without coder
   sign-off. Coder edits are data, and they drive the evaluation.
5. **Append-only history.** Drafts are immutable once generated; review
   actions are append-only events; the final claim is computed at sign-off;
   every state transition gets a ledger entry.
6. **Backward compatible.** Existing seeded claims (CLM-1001…, CLM-2001…)
   have no documents and status `PENDING`; they must still adjudicate
   exactly as they do today (the evidence check reports `NOT_APPLICABLE`).

---

## 3. Claim state machine

```
            upload
  (none) ─────────▶ DRAFT ──process──▶ PROCESSING ──ok──▶ READY_FOR_REVIEW
                      ▲                    │                     │
                      │                  error                coder opens
                      │                    ▼                     ▼
                      └──── retry ──── FAILED               IN_REVIEW
                                                                 │ sign-off
                                                                 ▼
                                                              PENDING
                                                                 │ adjudicate
                                                                 ▼
                                                           ADJUDICATING
                                                                 │
                                    ┌────────────────────────────┼─────────────┐
                                    ▼                            ▼             ▼
                                APPROVED                      DENIED     REQUEST_INFO
                                                                               │
                                                        more docs uploaded ────┘
                                                        → back to DRAFT (new draft version)
```

- Transitions are enforced in one place: `app/pipeline/state.py`
  (`transition(claim_id, from_states, to_state)` — raises 409 on an illegal
  transition). Every transition appends a ledger event.
- `status` stays on the existing `insurance-claims` document. Don't add a
  separate `status_history` field; the ledger already records the history.

---

## 4. Stage-by-stage specification

### Stage 1 — Ingestion

**Goal:** accept a bundle of documents from a hospital, store them
immutably, create the claim in `DRAFT`.

- **Endpoint:** `POST /claims/intake` (multipart)
  - form fields: `patient_id`, `payer_name`, `claim_type`, `submitted_by`
    (hospital/user id), optional `claim_id`
  - files: `files[]` (PDF, PNG, JPG, TIFF; reject others with 415; max size
    from config, default 20 MB each)
  - returns `{claim_id, status: "DRAFT", documents: [...]}`
- Keep `POST /claims` (manual entry → `PENDING`) and
  `POST /claims/{id}/documents` working for backward compatibility; the
  latter now also registers the document in `claim-documents` and, if the
  claim is in `REQUEST_INFO`, moves it back to `DRAFT`.
- **Storage:** keep local disk under `backend/uploads/{claim_id}/` behind a
  small interface `app/storage/blob_store.py`
  (`put(claim_id, doc_id, bytes, filename) -> uri`, `get(uri) -> bytes`) so
  S3 is a one-class swap (`S3BlobStore` using boto3, which is already a
  dependency). Never overwrite a stored file.
- **Per document record** → new index `claim-documents`:
  `doc_id, claim_id, filename, mime_type, size_bytes, sha256, source_uri,
  doc_type (referral_letter | op_note | discharge_summary | lab | rx | other,
  user-supplied or "other"), page_count (null until OCR), ocr_status
  (PENDING|DONE|FAILED), uploaded_at, uploaded_by`.
- The claim document in `insurance-claims` gains: `status: "DRAFT"`,
  `source: "intake" | "manual"`, `cpt_code`/`icd10_code` empty until
  sign-off, and keeps `attached_documents` (same shape as today).
- **Ledger events:** `CLAIM_CREATED`, one `DOCUMENT_UPLOADED` per file
  (payload includes the file `sha256` — this is what makes the whole chain
  anchor to the actual bytes).
- **Files:** new `app/routers/intake.py`, `app/storage/blob_store.py`,
  `app/indices/mappings/claim_documents.json`; modify `routers/claims.py`.
- **Accept when:** uploading the 3 KB `data/sample/sample_referral_letter.pdf`
  creates a `DRAFT` claim, the file is on disk, its sha256 is in
  `claim-documents`, and two ledger entries exist for the claim.

### Stage 2 — OCR

**Goal:** turn every document into page text with stable character offsets.

- **Engine order** (`app/ocr/extract.py`):
  1. `pdfplumber` text layer for PDFs (already a dependency). If a page
     yields ≥ 20 non-whitespace chars, use it (`engine: "pdf_text"`).
  2. Otherwise (scanned page / image file) → **AWS Textract**
     `DetectDocumentText` via boto3 (`engine: "textract"`), lines joined
     with `\n` in reading order. Config flag `ocr_provider` =
     `textract | tesseract | none`.
  3. If no OCR provider is available, mark the page `ocr_status: FAILED`
     and continue — the coder can still work, with fewer suggestions.
- **Normalization (do once, then never change the text):** NFC unicode,
  `\r\n → \n`, collapse runs of spaces to one, keep line breaks. Offsets are
  **Python `str` indices (code points) into the normalized page text.**
  (Frontend note: JS strings are UTF-16; highlight using
  `Array.from(pageText)` slicing or send pre-split segments from the API.)
- **Index `document-pages`:** `page_id` (`{doc_id}:p{n}`), `doc_id`,
  `claim_id`, `page_number` (1-based), `text`, `engine`, `ocr_confidence`
  (Textract mean, null for pdf_text), `char_count`.
- **Index `document-chunks`** (search units for stages 3 and 6):
  paragraph-ish windows of ~500–800 chars, split on blank lines/sentences,
  never crossing a page. Fields: `chunk_id`, `doc_id`, `claim_id`,
  `page_number`, `char_start`, `char_end` (offsets into that page's text),
  `text`, `section` (heuristic header like "Assessment", "Plan",
  "Medications", "Procedure" if detected, else null), `text_vector` (768-d
  via `embeddings/embed.py`, same `bbq_disk` config as other indices).
- **Invariant (unit-test it):** for every chunk,
  `page.text[chunk.char_start:chunk.char_end] == chunk.text`.
- **Ledger event:** `OCR_COMPLETED` with per-doc `{doc_id, page_count,
  engine, sha256_of_concatenated_page_text}`.
- **Files:** `app/ocr/extract.py`, `app/ocr/chunker.py`,
  `app/indices/mappings/document_pages.json`,
  `app/indices/mappings/document_chunks.json`.

### Stage 3 — Claim Draft Generation

Runs as one call: `POST /claims/{id}/process` → SSE stream (same event
style as `/adjudicate`, so the UI shows progress): `ocr_page`,
`candidates`, `draft_field`, `warning`, `done`. Moves the claim
`DRAFT → PROCESSING → READY_FOR_REVIEW` (or `FAILED`).

#### 3a. Candidate generation (deterministic) — `app/drafting/candidates.py`

A **candidate** = `{candidate_id, field_type, code_system, code, display,
span: {doc_id, page_number, char_start, char_end, text}, method, score}`.

- **Regex pass** over each page's text:
  - CPT: `\b\d{4}[0-9FTU]\b` (5-char; category II/III suffixes)
  - ICD-10-CM: `\b[A-TV-Z]\d[0-9A-Z](?:\.[0-9A-Z]{1,4})?\b`
  - Every regex hit is **kept only if it exists in the code dictionary**
    (kills false positives like dates and MRNs). `method: "regex"`.
- **Dictionary phrase pass:** for each chunk, BM25 search in
  `code-dictionary` over `display` + `synonyms` (e.g. "total knee
  arthroplasty" → 27447, "primary osteoarthritis, right knee" → M17.11).
  Span = the matched phrase inside the chunk (locate via highlighter
  offsets or a case-insensitive `find` on the chunk text, then shift by
  `chunk.char_start`). `method: "dictionary"`.
- **RxNorm pass** (`app/drafting/rxnorm.py`): tokenise medication-like
  lines (Medications / Plan / Rx sections first, then all text), look up
  each name in `rxnorm-concepts` (name + brand/generic synonyms, same
  whitespace+uppercase analyzer as `fda-drug-interactions`). Output
  `code_system: "RXNORM"`, `code: rxcui`, plus parsed `dose`/`frequency` if
  regex-extractable and a `status` hint (`active` / `new` / `discontinued`)
  from nearby words ("start", "initiate", "prescribed" → `new`; "continue",
  "home meds" → `active`; "stop", "d/c" → `discontinued`). Reuse / refactor
  `resolve_medication_to_rxnorm` from `tools/drug_interaction_tool.py` so
  there is one resolver.
- Negation guard: drop or down-score candidates in a sentence with
  "no", "denies", "rule out", "r/o", "history of" (history-of keeps the
  candidate but tags `context: "historical"`).
- De-duplicate by `(code_system, code)`, keeping all spans (a code with 3
  supporting spans is stronger).

**Reference data (new ingestion scripts):**
- `code-dictionary` index — `code_system` (CPT | ICD10CM | HCPCS), `code`,
  `display`, `synonyms`, `billable` (ICD leaf codes), `active`. Load from
  `data/codes/*.json` via `app/ingestion/load_code_dictionary.py`.
  - ICD-10-CM: public domain (CMS/CDC release) — load the full code set or
    at minimum every code referenced in sample/synthea data and policies.
  - CPT: **AMA-licensed** — ship only a small curated subset with our own
    short descriptions for codes used in the demo data (27447, 27130,
    97110, 70551, 93306, 22558, …) and say so in the README.
- `rxnorm-concepts` index — `rxcui`, `name`, `tty`, `synonyms` (brands),
  `ingredients`. Load a subset (all drugs in `fda-drug-interactions` +
  synthea meds) via `app/ingestion/load_rxnorm.py`; optional online
  fallback to NLM RxNav `approximateTerm` behind a config flag, cached.

#### 3b. LLM selection with citations — `app/drafting/draft_generator.py`

- Input to Claude: claim header (payer, claim_type), the candidate list
  (ids, code, display, span text, method, score, context), and the chunks
  those candidates came from (chunk ids + text). **No other text.**
- Output via a forced tool call (`tool_choice` = `submit_claim_draft`),
  schema:
  ```json
  {
    "fields": [
      {
        "field_type": "primary_cpt | secondary_cpt | primary_icd10 | secondary_icd10 | medication | date_of_service",
        "candidate_id": "CAND-…  (required for code/medication fields)",
        "value": "YYYY-MM-DD (date_of_service only)",
        "span_ids": ["CAND-…:span0"],
        "rationale": "≤ 200 chars, shown to coder, never used for decisions"
      }
    ],
    "unresolved": ["free-text notes on things the model could not code"]
  }
  ```
- **Server-side validation (the core of the zero-hallucination claim):**
  - `candidate_id` must exist in this run's candidate set → else drop field,
    emit `warning`.
  - every cited span must belong to that candidate (or, for
    `date_of_service`, be a span whose text contains the date) → else drop.
  - exactly one `primary_cpt` and one `primary_icd10`; extras demoted to
    secondary.
  - re-check `page_text[start:end] == span.text`.
- **Deterministic fallback** (no LLM / LLM error / validation dropped
  everything): primary = highest-scoring candidate per type (score =
  #spans × method weight: regex 1.0, dictionary 0.7; section bonus for
  "Procedure"/"Assessment"), all medication candidates included,
  `origin: "deterministic"`.
- **Index `claim-drafts`** (immutable, one doc per generation):
  `draft_id`, `claim_id`, `version` (1, 2, … — a new upload after
  `REQUEST_INFO` makes a new version), `generated_at`, `origin`
  (`llm` | `deterministic`), `model_id`, `candidates` (nested, full list —
  needed for evaluation), `fields` (nested: `field_id`, `field_type`,
  `code_system`, `code`, `display`, `value`, `spans[]`, `rationale`,
  `confidence`), `unresolved`.
- **Ledger event:** `DRAFT_GENERATED` (payload = the full draft doc).

### Stage 4 — Coder Review UI

**Goal:** a certified coder verifies every field against its source text.

- **Frontend:** new route `frontend/app/claims/[id]/review/page.tsx`.
  - Left pane: field list grouped (Procedures / Diagnoses / Medications /
    Date of service), each row = code, display, origin badge, confidence,
    action buttons **Accept · Edit · Reject**, status chip.
  - Right pane: document viewer — page text (from `document-pages`) with the
    selected field's spans highlighted and auto-scrolled; page tabs per
    document; link to the original file (`/files/...`).
  - Edit: typeahead against `GET /codes/search?system=ICD10CM&q=…`
    (code-dictionary); coder may attach a span by selecting text in the
    viewer (UI sends `doc_id, page, char_start, char_end`, server verifies
    the text).
  - Reject requires a reason (`not_supported | wrong_code | duplicate |
    historical | other` + free text).
  - "Add field" for codes the draft missed (`action: "add"`).
  - **Sign off** button enabled only when every field has a decision and
    there is exactly one accepted/edited primary CPT and primary ICD-10.
  - Reuse `StatusBadge`, `CitationPanel` styling; add a pipeline stepper
    component to `claims/[id]/page.tsx` showing the claim's current stage.
- **Endpoints** (`app/routers/review.py`):
  - `GET /claims/{id}/draft` — latest draft + current review state
  - `GET /claims/{id}/documents/{doc_id}/pages/{n}` — page text
  - `POST /claims/{id}/review/actions` —
    `{field_id | null, action: accept|edit|reject|add, new_code?,
    code_system?, spans?, reason?, coder_id}`; validates code exists in
    dictionary; first action moves `READY_FOR_REVIEW → IN_REVIEW`.
  - `POST /claims/{id}/sign-off` — `{coder_id, attestation: true}`
- **Index `review-actions`** (append-only; latest action per field wins):
  `action_id`, `claim_id`, `draft_id`, `field_id`, `action`,
  `before` (code/display), `after`, `spans`, `reason`, `coder_id`, `at`.
- **Ledger events:** one `FIELD_REVIEWED` per action, `CODER_SIGNED_OFF`.
- Auth is out of scope for the hackathon: `coder_id` is a header/body
  field. Note it in the README as a known limitation.

### Stage 5 — Final Claim (PENDING)

Computed at sign-off by `app/review/finalize.py` — pure function
`finalize(draft, actions) -> final_claim`:

- For each draft field take the latest action; accepted → draft value,
  edited → `after`, rejected → excluded; add `add` actions.
- Write onto the `insurance-claims` doc:
  - `cpt_code`, `icd10_code` = primary codes (**keeps the existing
    orchestrator, letter generator and UI working unchanged**)
  - new: `secondary_cpt_codes[]`, `secondary_icd10_codes[]`,
    `medications[]` (`{rxcui, name, status, dose, spans}`),
    `date_of_service`, `final_fields[]` (each with `provenance:
    draft_accepted | coder_edited | coder_added`, spans, draft_field_id),
    `draft_id`, `signed_off_by`, `signed_off_at`, `status: "PENDING"`.
- **Ledger event:** `CLAIM_FINALIZED` with payload = final fields + hash of
  the draft it came from. This is the "draft + coder changes saved" record.
- Update mapping `indices/mappings/insurance_claims.json` for the new
  fields (all additive).

### Stage 6 — Claim vs Evidence Check

**Goal:** before any payer logic, confirm the documents support the final
codes. Catches coder-added codes without evidence and upcoding.

`app/evidence/evidence_check.py` → `check_claim_evidence(claim) -> dict`,
run as the first step of `adjudicate_claim` (emit a `reasoning_step`).

For each final code:
1. **Direct span** — field already has spans that verify (text equality
   re-checked) → `SUPPORTED` (strength 1.0).
2. **Search** — no span (coder-added / edited without span): search
   `document-chunks` filtered to this `claim_id` with the code string +
   dictionary display + synonyms (BM25), plus kNN on `text_vector`, RRF
   fused (same pattern as `policy_matcher_tool.py`). Top hit containing
   the code or ≥ 60% of display tokens → `SUPPORTED` (strength 0.7) with
   that chunk as evidence; weaker hit → `WEAK`; none → `UNSUPPORTED`.
3. **Consistency rules** (deterministic, small table in
   `app/evidence/rules.py`): CPT/ICD pairing sanity from the matched policy's
   `icd10_codes` when available; laterality mismatch (ICD says right, text
   only says left) → `WEAK`.
4. Optional LLM verifier (config flag, off by default): given code + the
   candidate chunks, returns `supported: bool` + `span` that must pass the
   same verbatim check; it can only downgrade, never upgrade, a result.

Output (stored in `evidence-checks`, and passed to `_decide`):
`{claim_id, overall: SUPPORTED | PARTIAL | UNSUPPORTED | NOT_APPLICABLE,
codes: [{code, code_system, result, strength, evidence: [cited_evidence]}]}`.
Claims with no documents → `NOT_APPLICABLE` (seeded demo claims).
Evidence entries use the existing `cited_evidence` shape with
`source_index: "document-chunks"` and **real** offsets (replacing today's
`byte_offset_start: 0` placeholders for document evidence).

**Ledger event:** `EVIDENCE_CHECKED`.

### Stage 7 — Insurance Evaluator

Reuse `app/agent/orchestrator.py`. Changes only:

- Load the **final** claim (`status` must be `PENDING`; 409 otherwise) and
  transition to `ADJUDICATING`.
- Add the evidence-check summary and the claim's `medications[]` to the
  agent's initial user message.
- Drug interaction input: `new_medication_code` = medications with
  `status: "new"` from the documents; active = those with `active` plus
  EHR `MedicationRequest`s (existing `_get_patient_medications`). This
  replaces the deterministic sweep's `meds[-1]` "newest is new" heuristic;
  keep that heuristic only when the claim has no document medications.
  Check **each** new med, not only one.
- Trajectory: keep ES|QL over `fhir-clinical-ehr`; additionally let
  document chunks count as evidence of conservative therapy (e.g. "failed
  6 months of PT") by adding a `document_evidence` section to the
  trajectory result (search `document-chunks` for the therapy keywords).
  Report it as evidence, but only EHR-dated encounters compute
  `step_therapy_met` (dates in free text are not reliable enough).
- Policy match: fix the known exact-match payer filter by normalizing payer
  names (`app/tools/payer_normalize.py`: alias table, e.g. "UHC" →
  "UnitedHealthcare", "Medicare" → "Medicare (CMS Local Coverage
  Determination)").

### Stage 8 — Decision

Extend `_decide()` (still deterministic, still not the LLM) with explicit
precedence and a returned **reason code** list, so the letter and eval can
say *why*:

| # | Condition | Decision | reason_code |
|---|---|---|---|
| 1 | any interaction severity `Contraindicated` or `Major` | DENIED | `DRUG_INTERACTION` |
| 2 | evidence `overall == UNSUPPORTED`, or primary CPT/ICD `UNSUPPORTED` | REQUEST_INFO | `CODES_NOT_SUPPORTED` |
| 3 | no policy matched | REQUEST_INFO | `NO_POLICY_MATCH` |
| 4 | policy requires step therapy and trajectory not run | REQUEST_INFO | `STEP_THERAPY_UNVERIFIED` |
| 5 | policy requires step therapy and not met | DENIED | `STEP_THERAPY_NOT_MET` |
| 6 | evidence `PARTIAL` (secondary codes weak/unsupported) | APPROVED with flag | `PARTIAL_EVIDENCE` |
| 7 | otherwise | APPROVED | `CRITERIA_MET` |

Note rows 3 and 4 **change current behaviour** (today both fall through to
APPROVED). Check the seeded demo claims after the change and update the
README's expected outcomes. Store `status`, `reason_codes`, and
`decision_inputs` (the summarized facts each rule used) on the
`adjudication-results` doc; update its mapping.

### Stage 9 — Audit Ledger

Generalize `tools/audit_ledger.py` (keep the file and hash rule):

```
append_event(claim_id, event_type, actor, payload, ref_id=None) -> entry
record_hash = SHA256(canonical_json(entry_without_record_hash) )
entry = {ledger_id, claim_id, sequence_number, event_type, actor,
         ref_id, payload_hash = SHA256(canonical_json(payload)),
         payload, prev_hash, timestamp, record_hash}
```

- **Store the payload** (or for large payloads, the payload hash + the id of
  the doc it lives in). Today `verify_chain` can only check linkage because
  the payload is not stored; tampering with `adjudication-results` is
  undetectable. `verify_chain` must recompute every `record_hash` and every
  `payload_hash` and compare with the referenced source doc.
- **Concurrency:** index with explicit `_id = f"{claim_id}:{sequence_number}"`
  and `op_type="create"`; on a 409 conflict, re-read the tail and retry
  (max 3). Refresh after write (`refresh="wait_for"`).
- Keep `append_entry(...)` as a thin wrapper so existing callers/tests pass.
- Event types: `CLAIM_CREATED, DOCUMENT_UPLOADED, OCR_COMPLETED,
  DRAFT_GENERATED, FIELD_REVIEWED, CODER_SIGNED_OFF, CLAIM_FINALIZED,
  EVIDENCE_CHECKED, ADJUDICATED, OUTPUT_GENERATED, ALERT_RAISED,
  STATUS_CHANGED`.
- **Endpoints:** `GET /claims/{id}/ledger`, `GET /claims/{id}/ledger/verify`
  → `{intact: bool, first_broken_sequence: int | null}`. Wire the existing
  `frontend/app/audit-trail/page.tsx` to these.
- Update `indices/mappings/audit_ledger.json` (`event_type`, `actor`,
  `ref_id`, `payload_hash` keyword; `payload` as `flattened` or
  `enabled: false` object).

### Stage 10 — Output

- **Letter** (`actuators/letter_generator.py`, still templated, never
  LLM-written): add sections for final codes with provenance ("coded from
  referral letter p.1"), evidence-check result per code, reason codes, and
  for `REQUEST_INFO` a concrete list of what is missing (derived from
  reason codes + unsupported codes).
- **FHIR ClaimResponse:** extend `build_fhir_claim_response` with
  `outcome` (`complete` | `partial` | `queued`), `disposition` text,
  `item[]` per final CPT with `adjudication[]` (`category: submitted /
  eligible`, reason), `processNote[]` from reason codes, and
  `communicationRequest` hint for REQUEST_INFO. Validate the shape in a
  test against a minimal FHIR R4 JSON check (resourceType, required keys).
- **Alert:** new index `alerts` (`alert_id, claim_id, type:
  DRUG_INTERACTION | CODES_NOT_SUPPORTED | LEDGER_BROKEN, severity,
  message, created_at, acknowledged`). Raised by the orchestrator; still
  emitted as the existing `interaction_alert` SSE event; optional outbound
  webhook (`ALERT_WEBHOOK_URL` in config) — also usable from a Kibana
  alerting rule over `alerts`.
- **Ledger events:** `ADJUDICATED` (payload = adjudication doc),
  `OUTPUT_GENERATED` (hash of letter + FHIR JSON), `ALERT_RAISED`.

### Stage 11 — Evaluation

Two metric families, both computed from stored data — no hand-typed numbers.

**Extraction accuracy (from coder edits)** — `app/eval/extraction_metrics.py`,
exposed at `GET /eval/extraction` and printed by `eval/run_benchmark.py`:

Per signed-off claim, compare `claim-drafts.fields` vs final fields:

| Draft field outcome | Counts as |
|---|---|
| accepted unchanged | true positive |
| edited (code changed) | false positive + false negative |
| rejected | false positive |
| coder-added | false negative |

Report precision / recall / F1 per `field_type` and per `code_system`,
primary-code exact-match rate, **acceptance rate without edit**, citation
validity rate (spans that pass the verbatim check — should be 100%),
LLM vs deterministic origin breakdown, and top rejection reasons.

**Decision accuracy** — `eval/cases/*.json`: labelled cases =
documents + patient + payer + `expected_final_codes` +
`expected_decision` + `expected_reason_codes`. Build ≥ 20 from the
synthea patients and seeded policies (covering each row of the §8 table).
`run_benchmark.py` runs the whole pipeline headless (coder step simulated by
auto-accepting the expected codes, so extraction and decision are measured
separately) and reports: decision accuracy, confusion matrix over
APPROVED/DENIED/REQUEST_INFO, reason-code accuracy, policy recall@3,
trajectory accuracy, end-to-end p95 latency per stage. Writes
`benchmark_results.json` with the git SHA and timestamp.

---

## 5. Elasticsearch indices (summary)

| Index | Status | Written by | Key fields |
|---|---|---|---|
| `insurance-claims` | modify | intake, finalize, orchestrator | + status values, `source`, secondary codes, `medications`, `final_fields`, `draft_id`, sign-off |
| `claim-documents` | new | stage 1/2 | doc_id, claim_id, sha256, source_uri, page_count, ocr_status |
| `document-pages` | new | stage 2 | page_id, doc_id, page_number, text, engine |
| `document-chunks` | new | stage 2 | chunk_id, page_number, char_start/end, text, section, text_vector |
| `code-dictionary` | new | ingestion | code_system, code, display, synonyms |
| `rxnorm-concepts` | new | ingestion | rxcui, name, synonyms, tty |
| `claim-drafts` | new | stage 3 | draft_id, version, origin, candidates, fields |
| `review-actions` | new | stage 4 | field_id, action, before, after, coder_id |
| `evidence-checks` | new | stage 6 | overall, codes[] |
| `adjudication-results` | modify | stage 8/10 | + reason_codes, decision_inputs, evidence_check_id |
| `audit-ledger` | modify | all | + event_type, actor, payload, payload_hash |
| `alerts` | new | stage 10 | type, severity, acknowledged |
| `medical-policies`, `fhir-clinical-ehr`, `fda-drug-interactions` | unchanged | — | — |

All new mappings go in `app/indices/mappings/` and are registered in
`app/indices/create_indices.py`.

---

## 6. API surface (summary)

| Method | Path | Stage |
|---|---|---|
| POST | `/claims/intake` | 1 |
| POST | `/claims/{id}/documents` (existing, extended) | 1 |
| POST | `/claims/{id}/process` (SSE) | 2–3 |
| GET | `/claims/{id}/documents` | 2 |
| GET | `/claims/{id}/documents/{doc_id}/pages/{n}` | 4 |
| GET | `/claims/{id}/draft` | 4 |
| POST | `/claims/{id}/review/actions` | 4 |
| POST | `/claims/{id}/sign-off` | 5 |
| GET | `/codes/search?system=&q=` | 4 |
| POST | `/claims/{id}/adjudicate` (existing SSE; now runs 6–10) | 6–10 |
| GET | `/claims/{id}/ledger`, `/claims/{id}/ledger/verify` | 9 |
| GET | `/alerts`, POST `/alerts/{id}/ack` | 10 |
| GET | `/eval/extraction` | 11 |

SSE event names stay compatible with the current frontend parser in
`claims/[id]/page.tsx` (`reasoning_step`, `interaction_alert`, `done`,
`error`), adding `evidence_check`, `ocr_page`, `candidates`,
`draft_field`, `warning`.

---

## 7. Target code layout

```
backend/app/
  routers/        claims.py (mod), adjudication.py (mod), patients.py,
                  intake.py, processing.py, review.py, codes.py, ledger.py,
                  alerts.py, eval.py
  pipeline/       state.py            — status transitions + ledger hook
  storage/        blob_store.py       — LocalBlobStore / S3BlobStore
  ocr/            extract.py, chunker.py
  drafting/       candidates.py, rxnorm.py, draft_generator.py, prompts.py
  review/         finalize.py
  evidence/       evidence_check.py, rules.py
  agent/          orchestrator.py (mod: final claim, evidence, meds, _decide)
  tools/          audit_ledger.py (generalized), payer_normalize.py,
                  trajectory_tool.py, policy_matcher_tool.py,
                  drug_interaction_tool.py
  actuators/      letter_generator.py (mod), alerts.py
  eval/           extraction_metrics.py
  ingestion/      + load_code_dictionary.py, load_rxnorm.py
  indices/mappings/ + the new JSON mappings from §5
backend/tests/    test_ocr_offsets.py, test_candidates.py,
                  test_draft_validation.py, test_finalize.py,
                  test_evidence_check.py, test_decide.py,
                  test_ledger_verify.py, test_pipeline_e2e.py
frontend/app/
  claims/new/page.tsx         (mod: upload-first intake)
  claims/[id]/review/page.tsx (new: coder review)
  claims/[id]/page.tsx        (mod: pipeline stepper, evidence panel)
  audit-trail/page.tsx        (wire to ledger endpoints)
  reports/page.tsx            (extraction + decision metrics)
  components/ DocumentViewer.tsx, FieldReviewRow.tsx, PipelineStepper.tsx
data/
  codes/icd10cm_subset.json, cpt_demo_subset.json, rxnorm_subset.json
  sample/documents/           (demo PDFs per demo claim)
eval/
  cases/*.json, run_benchmark.py (implemented)
```

New Python deps: none required (pdfplumber, boto3 already present).
Optional: `pytesseract` only if `ocr_provider=tesseract`. Bump `anthropic`
only if forced `tool_choice` needs it.

---

## 8. Configuration additions (`app/config.py`)

```
ocr_provider: str = "textract"        # textract | tesseract | none
max_upload_mb: int = 20
drafting_use_llm: bool = True          # False → deterministic drafting only
evidence_llm_verifier: bool = False
rxnav_online_fallback: bool = False
alert_webhook_url: str | None = None
blob_store: str = "local"              # local | s3
s3_bucket: str | None = None
```

Mirror every key in `backend/.env.example` with a comment. No secrets in
code or commits.

---

## 9. Build phases (in order; each ends green)

1. **Foundation** — generalized ledger (+ verify, concurrency), state
   machine, new mappings, `create_indices` update, blob store.
   *Done when:* existing tests pass; `test_ledger_verify` detects a
   tampered payload.
2. **Ingestion + OCR** — `/claims/intake`, `claim-documents`, OCR
   extraction, pages + chunks. *Done when:* offset invariant test passes on
   the sample PDF and a scanned-image fixture (or is skipped with a clear
   message when no OCR provider is configured).
3. **Reference data + candidates** — code dictionary, RxNorm subset,
   candidate generation. *Done when:* the demo documents yield the expected
   codes (e.g. 27447 / M17.11 for the knee case) as candidates, with spans.
4. **Draft generation** — LLM selection + validator + deterministic
   fallback, `/process` SSE. *Done when:* a test with a mocked LLM that
   returns an invented code and a bogus span shows both being dropped.
5. **Coder review + finalize** — endpoints, review UI, sign-off, final
   claim. *Done when:* accept/edit/reject/add round-trip produces the
   expected final claim and ledger events.
6. **Evidence check + evaluator changes + decision table** — *Done when:*
   `test_decide` covers every row of the §4-Stage-8 table and seeded claims
   CLM-1001, CLM-2001…2005 still adjudicate (expected outcomes updated in
   README where rules 3/4 change them).
7. **Output + alerts** — letter/FHIR extensions, alerts index + webhook.
8. **Evaluation** — extraction metrics endpoint, labelled cases,
   implemented `run_benchmark.py`, reports page.
9. **Docs** — README quickstart for the new flow; fill in `SUBMISSION.md`
   architecture section from this file.

---

## 10. Rules for the building model

- Read the existing module before changing it; match its style (module
  docstring explaining *why*, small functions, `es.search` with explicit
  `index=`, `.body` on responses).
- **Never** let an LLM produce a code, drug, decision, citation, or letter
  sentence that is not validated against stored data. If validation fails,
  drop the value and emit a `warning` — do not "fix it up".
- Every LLM call has a deterministic fallback path and records
  `origin` + `model_id`.
- Every state change goes through `pipeline/state.py` and writes a ledger
  event. No direct `status` writes elsewhere.
- Offsets are code-point indices into normalized page text; assert the
  verbatim invariant wherever a span is created or received from the UI.
- Do not break existing endpoints or SSE event names; existing seeded
  claims must keep working.
- Do not fabricate data, benchmark numbers, or code descriptions presented
  as official. CPT descriptors are licensed — use our own short
  descriptions for the demo subset.
- Tests run against a real Elasticsearch (same as today's
  `tests/test_tools.py`); pure logic (`finalize`, `_decide`, validators,
  chunker, candidate regexes) gets unit tests that need no cluster.
- Keep secrets in `.env`; add every new setting to `.env.example`.
