# MediAudit-X

Forge the Future Hackathon 2026 · Elastic + AWS + Sarvam

**Claims you can cite, not just trust.**

A zero-hallucination clinical claims auditor. Every adjudication decision
is grounded in real Elasticsearch search results — hybrid BM25 + vector
search with RRF, and ES|QL temporal queries — and cited back to its
source, rather than left to LLM inference alone.

## Core capabilities

- **Document intake + OCR** (`pipeline/ingestion/` + `pipeline/ocr/`,
  see `INGESTION.md` and `OCR.md`) — a hospital uploads PDFs/images against a claim;
  each file is validated (magic-byte content sniffing, size/page/pixel
  limits, duplicate detection), stored, and registered in `claim-documents`
  with `ocr_status: PENDING`. `POST /claims/{claim_id}/ocr` then extracts
  every PENDING document's text (pdfplumber's embedded text layer first,
  Tesseract OCR for scanned pages and images -- AWS Textract is spec'd as
  an alternative engine but not implemented; `ocr_provider` in
  `config.py` selects between them) and writes offset-addressable chunks
  to `document-chunks` (with embeddings, ready for the same RRF hybrid
  search pattern policy matching uses) so every extracted fact can cite
  back to `(doc_id, page, char_start, char_end)`.
- **Logging & monitoring** (`observability/`, see `MONITORING.md`) — not
  part of the original stage plan, added afterward once the codebase had
  routers/pipelines converting most errors to clean HTTP responses but
  nothing actually visible when something unexpected went wrong. Every
  request and every `logger.x(...)` call anywhere in `app/` is
  structured-JSON logged to stdout and (optionally) shipped to a new
  `app-logs` Elasticsearch index, correlated by `request_id`/`claim_id`,
  off a background thread so an Elasticsearch write never blocks the
  request it's describing. Deliberately a separate index from
  `ARCHITECTURE.md`'s planned business-domain `alerts` index (Stage 10) —
  this is infra/app observability, not claims-review alerting.
- **Clinical trajectory search** (`trajectory_tool.py`) — a real ES|QL
  bi-temporal query (with a DSL aggregation fallback) that verifies
  step-therapy timelines against actual longitudinal patient history,
  computing `step_therapy_met` from real encounter data rather than
  asserting it.
- **Hybrid policy matcher** (`policy_matcher_tool.py` +
  `embeddings/embed.py`) — RRF hybrid search (BM25 + a 768-dim vector)
  over payer policy documents, so exact code matches and semantically
  similar language (e.g. "Toradol" vs. "Ketorolac") both surface.
- **Drug interaction auditor** (`drug_interaction_tool.py`) — RxNorm
  brand/generic name resolution against FDA-flagged interaction pairs,
  so a brand-name/generic-name mismatch doesn't hide a real
  contraindication.
- **Agent orchestrator** (`agent/orchestrator.py`) — a multi-round Claude
  tool-use loop (via AWS Bedrock by default, direct Anthropic API as a
  local-dev fallback) that streams its reasoning live over SSE, assembles
  cited evidence with real source IDs, and writes to a hash-chained audit
  ledger. The final APPROVE/DENY/REQUEST_INFO decision is computed
  deterministically from tool results (`_decide()`), never left to the
  LLM to state, to preserve the zero-hallucination property. Falls back
  to a deterministic no-LLM tool sweep if the LLM call fails for any
  reason, so adjudication still completes end-to-end.
- **Claim chat** (`routers/chat.py`, `agent/chat.py` + `agent/chat_agent_builder.py`) —
  lets a reviewer ask free-text questions about one claim ("was step
  therapy met?", "why was this denied?") from the same real data, not a
  canned/demo response. Two interchangeable backends, selected by
  `CHAT_PROVIDER`: **Elastic Agent Builder** (default, if
  `KIBANA_URL`/Agent Builder is configured) — Kibana's own agent/tool
  orchestration, calling 3 custom ES|QL tools
  (`app/setup_agent_builder.py`) provisioned against `fhir-clinical-ehr`,
  `medical-policies`, and `fda-drug-interactions`, with server-side
  conversation state (`conversation_id`) — or the hand-rolled
  Bedrock/Anthropic tool loop reusing `agent/orchestrator.py`'s own
  tools. A converse call erroring on the Agent Builder side falls back
  to the Bedrock path automatically, same "always have a working
  fallback" rule the rest of this codebase follows. Deliberately kept to
  read-only Q&A, never the adjudication decision itself — a real
  difference in analysis style was found during development (Agent
  Builder's LLM reasoning over raw encounter data surfaced an NSAID
  prescription a keyword-based tool missed), useful for an explain-it-to-
  a-reviewer chat but not something to let override a deterministic
  decision.
- **Letter + FHIR generation** (`actuators/letter_generator.py`) —
  template-based, not LLM-freeform, built entirely from cited tool
  results.
- **Audit ledger** (`tools/audit_ledger.py`) — SHA-256 hash-chained,
  tamper-evident record of every adjudication.

## Data

- `data/sample/` — hand-built fixture claims, patients, and two
  drug-interaction pairs (Warfarin+Fluconazole, Apixaban+Ketorolac) with
  verified real RXCUI codes and FDA label citations.
- `data/synthea_samples/` — real Synthea-generated patient data (FHIR
  bundles from a synthetic Massachusetts population), with five curated
  demo claims:
  - **CLM-2001 / CLM-2003** — real knee/hip osteoarthritis patients with
    no documented conservative-therapy history, so the trajectory tool
    correctly reports zero evidence rather than a fabricated "almost
    enough" duration. CLM-2003's payer is set to
    `Medicare (CMS Local Coverage Determination)` to exactly match the
    real CMS policy data below, so it's the one claim that demonstrates a
    real Medicare policy match end-to-end.
  - **CLM-2002** — a real Warfarin + Ciprofloxacin overlap (`INT-3`).
  - **CLM-2004** — a real Warfarin (atrial fibrillation) + Aspirin
    (post-MI) overlap (`INT-4`) between two independently reasonable
    prescriptions.
  - **CLM-2005** — a real Lisinopril + Losartan dual RAAS-blockade
    combination (`INT-5`, severity `Moderate` — the set's first
    non-`Major`/`Contraindicated` pair).
  - Load with `python -m app.ingestion.ingest_synthea_samples` (after
    `load_sample_data`).
- `data/real_cms_lcd_policies.json` — two real, currently active Medicare
  LCDs: **L36575 "Total Knee Arthroplasty"** (CPT 27447) and **L34163
  "Total Hip Arthroplasty"** (CPT 27130), both adopted by Noridian
  Healthcare Solutions, LLC. Extracted from CMS's own bulk LCD database
  export via `extract_real_cms_lcds.py`, which takes the unzipped CSV
  directory as an argument, so pulling additional real LCDs is a config
  change (add the `lcd_id` to `TARGET_LCD_IDS`), not new plumbing. Load
  with `python -m app.ingestion.load_real_cms_policies`.
  - **Worth knowing:** unlike the hand-authored sample policy (which
    specifies "6 months of physical therapy"), the real Medicare LCD does
    *not* specify a fixed therapy duration — it requires only that
    "unsuccessful conservative therapy" be "clearly addressed in the
    pre-procedure medical record." `step_therapy_required` correctly
    computes to `False` for both real LCDs as a result — Medicare's
    national policy is genuinely less prescriptive here than commercial
    payer policy, not a bug.
  - ICD-10 codes are deliberately left blank on these two docs — that
    field isn't present in this CSV export (CMS ships it separately) —
    left empty rather than guessed.

## Known limitations

- **Logging/monitoring can lose the tail end of its logs on a hard
  process kill** (the background shipper thread is a daemon thread by
  design, flushed on a clean shutdown but not on `kill -9`), and
  **request duration on the SSE adjudication endpoint only measures
  time-to-first-byte, not the full streamed session** (a
  `BaseHTTPMiddleware` limitation). Neither affects `audit-ledger`, which
  is what actually needs to never lose an entry. See `MONITORING.md` §6.
- **On this project's real Elastic Cloud Serverless cluster, `dense_vector`
  fields (`policy_vector`, `notes_vector`, `document-chunks.text_vector`)
  never come back in `_source` — not via `GET`, not via `_search` hits —
  even though indexing reports success.** Verified this is not data loss:
  a direct `knn` query against a freshly indexed vector field ranked
  three test documents by real similarity (1.0 / 0.79 / 0.5), so the
  vectors are genuinely indexed and searchable; Elasticsearch Serverless
  just doesn't reconstruct `dense_vector` into synthetic `_source`,
  reproduced even with `index: false` (no quantization at all), so it's
  not specific to the `bbq_disk` index_options either. No code in this
  repo reads a vector value back out of a search hit (`policy_matcher_tool.py`
  only ever uses `policy_vector` as a `knn` query's field name), so this
  has no functional impact on hybrid search today — but don't add code
  that expects to read a stored vector back from `_source` on this
  cluster, and don't mistake a missing `policy_vector` key in a fetched
  document for evidence that embedding backfill didn't run.
- **Two pre-existing test failures on this real cluster, unrelated to the
  OCR work above, not yet investigated or fixed:**
  - `test_resolve_medication_to_rxnorm` expects RXCUI `6960` for
    "Toradol" but the cluster returns `35827` — exactly the kind of
    hand-typed-RXCUI mismatch this repo's golden rule exists to catch;
    needs someone to check `data/sample/sample_drug_interactions.json`
    against a live RxNav lookup for Toradol before trusting either number.
  - `test_audit_ledger_detects_tampering` fails because the ledger already
    has 6 entries under the hardcoded claim_id `CLM-TEST-TAMPER` (the test
    only appends 3), including one with a literal `record_hash: "TAMPERED"`
    left over from an earlier manual tampering-detection experiment. The
    chain-break `verify_chain` reports is real and correct given that
    history — the test itself needs a unique claim_id per run (or a
    teardown step) rather than reusing a fixed id against a shared,
    append-only, real cluster. Left as-is rather than deleting ledger
    entries unilaterally.
- **Policy matcher's payer-name filter is exact-match.** The two real
  Medicare policies are indexed with
  `payer_name: "Medicare (CMS Local Coverage Determination)"`; most
  sample claims use commercial payer names (UnitedHealthcare, Aetna,
  Cigna, Humana), so only claims using the exact Medicare payer name
  (CLM-2003) will match those two policies. Fixing this — normalizing
  payer names or relaxing the filter — is a known open item.
- **Bedrock model ID needs verifying per AWS account.** `BEDROCK_MODEL_ID`
  in `.env.example` is a best-effort default; Bedrock requires explicit
  per-model access approval (AWS Console → Bedrock → Model access) and
  exact model ID strings can differ by account/region. Confirm it works
  against a live Bedrock call before relying on it — the deterministic
  no-LLM fallback covers you if it doesn't.
- **Claim document storage is local disk**, not an object store — files
  uploaded via `POST /claims/{claim_id}/documents` are written under
  `backend/uploads/` (gitignored) and won't survive a redeploy. Swapping
  the local-disk write for an S3 `put_object` call is a contained change
  if needed (`attached_documents`'s shape doesn't need to change).
- **The embedding function is hashing-based, not a real transformer
  model** — dependency-light by design; see `embeddings/embed.py`'s
  docstring for the one-function swap path if a real model is available.
- **`eval/run_benchmark.py` is still a skeleton** — needs real test cases
  with known ground truth and real metric computation wired in; don't
  cite benchmark numbers that aren't produced by this script.
- **Elastic Agent Builder vs. the current hand-rolled Claude loop** is
  still undecided.
- **No Elastic webhook/email action wired up yet.**
- **OCR needs the Tesseract binary installed separately — it is not in
  requirements.txt and cannot be, since it isn't a Python package.**
  `pytesseract` (in requirements.txt) is only a wrapper that shells out to
  a `tesseract` executable. `pip install -r requirements.txt` alone will
  not give you working OCR on scanned pages/images:
  - Windows: `winget install UB-Mannheim.TesseractOCR`
  - macOS: `brew install tesseract`
  - Linux: `apt-get install tesseract-ocr`

  If it's missing, nothing crashes — `app/ocr/extract.py` degrades to
  `engine: "failed"` with empty text rather than guessing — but scanned
  documents/images will silently produce no extracted text until it's
  installed. This also applies to wherever the backend eventually gets
  deployed (a container image, a VM, etc.): Elasticsearch Serverless is
  only the search/data layer and never runs this Python app, so whatever
  environment does run it needs the same OS-level `tesseract-ocr` package
  baked in, in addition to `pip install -r requirements.txt`. The backend
  `Dockerfile` already does this (`apt-get install -y tesseract-ocr`) --
  see "Quickstart — Docker" below.

## Quickstart — Docker (recommended)

Needs Docker Desktop. Runs the backend and frontend against the
Elasticsearch configured in `backend/.env`; missing indices are created
automatically.

```bash
cd src/mediaudit-x
cp backend/.env.example backend/.env   # then set ELASTIC_URL or ELASTIC_CLOUD_ID + ELASTIC_API_KEY
docker compose up --build              # first run; later runs: docker compose up
```

- UI: http://localhost:3000 · API docs: http://localhost:8000/docs
- Stop: `Ctrl+C`, or `docker compose down`
- Elasticsearch running on your Mac itself? Use
  `ELASTIC_URL=http://host.docker.internal:9200` in `backend/.env`
- Sample data loads only when `insurance-claims` is empty; set
  `SEED_SAMPLE_DATA=false` in `backend/.env` to skip it
- Port already in use? `BACKEND_PORT=8001 docker compose up` (also
  `FRONTEND_PORT`)
- Code in `backend/app` and `frontend/app` hot-reloads; rebuild with
  `--build` after changing `requirements.txt` or `package.json`

Where data goes:

| What | Where |
|---|---|
| Claims created by uploading documents | `claim-files` index |
| Manual and sample claims | `insurance-claims` index |
| Uploaded document details (doc_id, name, type, pages, size, sha256, path) | `claim-documents` index |
| Hash-chained history of every upload | `audit-ledger` index |
| The uploaded files themselves | `uploads` Docker volume (`/app/uploads/{claim_id}/{doc_id}.pdf`) |

## Quickstart — running locally without Docker

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill in Elastic + AWS/Anthropic credentials
```

Also install the Tesseract OCR binary separately (needed for scanned
documents/images — see "Known limitations" below for why `pip install`
alone doesn't cover this): `winget install UB-Mannheim.TesseractOCR`
(Windows), `brew install tesseract` (macOS), or `apt-get install
tesseract-ocr` (Linux).

### 2. Create indices

```bash
python -m app.indices.create_indices
```

### 3. Load sample data

```bash
python -m app.ingestion.load_sample_data
python -m app.ingestion.load_real_cms_policies
python -m app.ingestion.ingest_synthea_samples   # CLM-2001 through CLM-2005
```

All three backfill `notes_vector` / `policy_vector` with the real
embedding function before indexing.

If `KIBANA_URL` is set and Agent Builder is enabled on your Elastic
project, also provision the claim-chat tools/agent (safe to re-run):

```bash
python -m app.setup_agent_builder
```

### 4. Run the backend

```bash
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 5. Run the tests

```bash
cd backend && python -m pytest tests/ -v
```

Requires steps 2-3 to have run first against the same cluster. (To run
the backend in Docker instead of this local venv, see "Quickstart —
Docker" above -- `docker-setup.sh` covers the equivalent of steps 2-3
automatically.)

### 6. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:3000 — click into a claim (e.g. CLM-1001) and run
adjudication to see the live agent reasoning stream, timeline, interaction
alert, and citation panel. Use "+ New Claim" to create and adjudicate a
new claim, optionally attaching supporting documents.

## Project layout

```
backend/app/
  routers/       FastAPI endpoints (claims, intake, ocr, adjudication, patients)
  pipeline/
    ingestion/    document upload -> checks -> storage -> claim-files/claim-documents (see INGESTION.md)
    ocr/          claim-documents (PENDING) -> extract + chunk -> document-pages/document-chunks
  observability/  structured logging (stdout + app-logs), request middleware (see MONITORING.md)
  agent/          orchestrator.py — the agent loop
  tools/          trajectory / policy matcher / drug interaction / audit ledger
  actuators/      letter + FHIR ClaimResponse generation
  embeddings/     embed.py — vector embedding function
  ingestion/      one script per seed data source (data/sample, CMS LCDs, Synthea) -- not to be
                  confused with pipeline/ingestion/, the live document-upload stage above
  indices/        Elasticsearch index mappings + names.py constants
frontend/app/      Next.js dashboard, claim detail, new-claim form
data/               sample/ and synthea_samples/ fixture data
eval/               benchmark harness (skeleton)
```

See `data/sample/` for the fixture claim/patient (CLM-1001 / PAT-883910)
built to trigger both the step-therapy denial path and a drug interaction
alert.
