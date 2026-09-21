# Architecture

How a claim moves from uploaded PDF to a cited, hash-chained decision.

Stage numbers below are the ones referenced in source comments
(`ARCHITECTURE.md Stage 6`, and so on).

```
 Hospital side                         Insurance side
 ─────────────                         ──────────────
 Stage 1   Intake                      Stage 6   Claim vs evidence check
   upload -> validate -> store                     do the docs support the codes?
   claim-files / claim-documents                        │
         │                                              ▼
         ▼                             Stage 7   Grounded tools
 Stage 2   OCR                                   policy matcher   (RRF hybrid)
   pdfplumber text layer, then                   trajectory       (ES|QL)
   Tesseract for scans                           drug interaction (RxNorm)
   document-pages / document-chunks                     │
         │                                              ▼
         ▼                             Stage 8   _decide()
 Stage 3   Claim draft (3a: codes)               deterministic fold, no LLM
   regex + dictionary candidates                        │
   LLM ranks, every field cites a span                  ▼
         │                             Stage 9   Audit ledger
         ▼                                       hash-chained, append-only
 Stage 4   Coder review                                 │
   accept / edit / sign off                             ▼
         │                             Stage 10  Output
         ▼                                       letter + FHIR ClaimResponse
 Stage 5   Final claim (PENDING) ──────▶         alerts index (not built)
                                                        │
                                                        ▼
                                       Stage 11  Evaluation
                                                 eval/run_benchmark.py
```

## Stage 1 — Intake

`pipeline/ingestion/`. A hospital uploads PDFs or images against a claim. Each
file is validated by magic-byte content sniffing rather than its extension,
with size, page-count, and pixel limits, plus SHA-256 duplicate detection.
Files land in `uploads/{claim_id}/{doc_id}.pdf` and register in
`claim-documents` with `ocr_status: PENDING`.

Claims live in two indices: `claim-files` for claims created by upload (DRAFT
first) and `insurance-claims` for manual and seeded claims. Lookups by
`claim_id` search both via the `ALL_CLAIMS` constant.

## Stage 2 — OCR

`pipeline/ocr/`. `POST /claims/{claim_id}/ocr` processes every PENDING
document. pdfplumber's embedded text layer is tried first; Tesseract handles
scanned pages and images. Output is written as offset-addressable chunks to
`document-pages` and `document-chunks`, with embeddings, so any extracted fact
can cite back to `(doc_id, page, char_start, char_end)`.

`ocr_provider` in `config.py` selects the engine. Only `tesseract` is
implemented — `textract` is specified but has no backend, and scanned pages
return `ocr_status: FAILED` if OCR is disabled.

Tesseract is imperfect in ways the downstream code accounts for: it silently
misreads `0` as `@` on some scans, which is why code extraction corroborates
across mentions rather than trusting a single hit.

## Stage 3 / 3a — Claim draft

`tools/claim_draft_tool.py` + `drafting/`. Hybrid, deliberately neither
pure-LLM nor pure-dictionary:

- `drafting/candidates.py` runs deterministic regex and local-dictionary
  lookup over OCR'd page text to propose CPT/ICD-10/RxNorm candidates.
- The LLM ranks those candidates. It never invents one.
- Every drafted field carries `{cited_text, doc_id, page_number}`.

The draft is in-memory until a coder accepts it. This stage does not create
claims or ingest anything — the claim already exists from Stage 1.

## Stage 4 — Coder review

A human accepts, edits, or signs off on the draft. The claim's
`cpt_code` / `icd10_code` / `claim_amount` — null until now — get filled in.

Coder edits are also the ground truth for extraction accuracy in Stage 11.

## Stage 5 — Final claim

The signed-off claim becomes PENDING and is handed to the insurance side.

## Stage 6 — Claim vs evidence check

`evidence/evidence_check.py`. Runs first inside `adjudicate_claim()`, before
any payer logic, and asks a narrow question: do the attached documents
actually support the claim's final codes? It catches coder-added codes with no
supporting text, and upcoding.

Deterministic, no LLM, three paths:

- **Direct span** — a code whose `extracted_*` entry still verifies against
  `document-pages.text` is SUPPORTED at full strength, no search needed.
- **Search** — a code with no span (hand-typed, or coder-added) is searched for
  in the claim's OCR page text, by code string or curated synonym.
- **NOT_APPLICABLE** — a claim with no documents at all, which includes every
  seeded demo claim. This is not a failure; those claims adjudicate normally.

The module only reads. The caller persists the result to `evidence-checks`.

## Stage 7 — The grounded tools

`agent/orchestrator.py` runs a multi-round Claude tool-use loop over AWS
Bedrock (Anthropic API as local-dev fallback), streaming reasoning over SSE.
The system prompt instructs it to call tools and explicitly not to state facts
no tool returned. It is not asked to write a verdict.

**Policy matcher** (`tools/policy_matcher_tool.py`) — RRF fusion of BM25 and a
dense vector over payer policies. BM25 boosts `cpt_codes^4`, `icd10_codes^3`,
`clinical_indications^2`, then `title`, because exact-code precision is the
whole thesis: semantic similarity alone conflates Type 1 and Type 2 diabetes,
which is the exact failure this project exists to prevent.

**Clinical trajectory** (`tools/trajectory_tool.py`) — a real ES|QL bi-temporal
query, with a DSL aggregation fallback, that computes `step_therapy_met` from
actual encounter history and required duration rather than asserting it.

**Drug interactions** (`tools/drug_interaction_tool.py`) — resolves brand and
generic names through RxNorm, then checks openFDA-flagged pairs, so a
brand/generic mismatch cannot hide a contraindication. Active medications are
pulled from the patient record when the model does not supply them.

## Stage 8 — The decision

`_decide()` in `agent/orchestrator.py`. A pure fold over tool results, in
order:

1. Any interaction of severity `Contraindicated` or `Major` → **DENIED**.
2. Evidence check `UNSUPPORTED` → **REQUEST_INFO**.
3. Matched policy requires step therapy → `step_therapy_met` decides
   **APPROVED** or **DENIED**.
4. No tool returned anything at all → **REQUEST_INFO**.
5. Otherwise → **APPROVED**.

This is the zero-hallucination property. An LLM that could write the verdict or
invent the citation would defeat the point of the system. If the LLM call fails
for any reason, a deterministic no-LLM tool sweep runs the same tools and the
same fold, so adjudication still completes end to end.

## Stage 9 — Audit ledger

`tools/audit_ledger.py` appends to `audit-ledger`, where each entry's
`record_hash = SHA256(canonical_json(payload) + prev_hash)`, chaining from
`GENESIS`. Editing any past entry breaks every subsequent hash, detectable in a
single linear scan. Tamper-evidence without blockchain overhead.

`append_event()` records the lifecycle too — `EVIDENCE_CHECKED`,
`ADJUDICATED`, `OUTPUT_GENERATED`, `ALERT_RAISED` — under the same hash rule.

## Stage 10 — Output

`actuators/letter_generator.py` produces a templated decision letter — never
LLM-written — and a FHIR R4 ClaimResponse.

A persisted `alerts` index is specified here but not built; drug-interaction
alerts currently surface only as the `interaction_alert` SSE event.

## Stage 11 — Evaluation

`eval/run_benchmark.py` measures tool-level retrieval and end-to-end verdict
accuracy from stored data, writing `benchmark_results.json` and
`e2e_benchmark_results.json`. The plan also specifies extraction accuracy
derived from coder edits, comparing draft fields against final signed-off
fields; that half is not implemented.

Results and their caveats are in the README.

## Cross-cutting: observability

`observability/`. Every request and every `logger.x(...)` call in `app/` is
emitted as structured JSON to stdout and, optionally, shipped to an `app-logs`
index, correlated by `request_id` and `claim_id`. Shipping happens on a
background thread so an Elasticsearch write never blocks the request it
describes.

This is deliberately a separate index from the planned business-domain alerts
of Stage 10 — this is infrastructure observability, not claims-review alerting.

## Indices

| Index | Holds |
|---|---|
| `insurance-claims` | Manual and seeded sample claims |
| `claim-files` | Claims created by document upload (DRAFT first) |
| `claim-documents` | Per-document metadata: doc_id, name, type, pages, size, sha256, path |
| `document-pages` | Extracted page text |
| `document-chunks` | Offset-addressable chunks with embeddings |
| `evidence-checks` | Stage 6 results |
| `audit-ledger` | Hash-chained decision history |
| `app-logs` | Structured application logs |

Uploaded files themselves live on disk (or a Docker volume) at
`/app/uploads/{claim_id}/{doc_id}.pdf`, not in Elasticsearch.

## The embedding

`embeddings/embed.py` is 768-dimensional deterministic feature hashing —
unigram and bigram tokens, TF weighting, L2 normalization — not a neural
embedding. It was chosen for the hackathon because a transformer model means a
1–2 GB download over venue wifi and a first-call load penalty during a live
demo.

It captures shared vocabulary, not meaning. RRF compensates by leaning on BM25
for the exact-code matching that drives precision here. Swapping in
`all-mpnet-base-v2` (also 768-dim) is a one-function change, since nothing
downstream knows anything but the `str -> list[float]` contract.
