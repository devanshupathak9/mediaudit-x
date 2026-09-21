# MediAudit-X

**Claims you can cite, not just trust.**

A zero-hallucination clinical claims auditor. Every adjudication decision is
grounded in real Elasticsearch results and cited back to its source, rather
than left to LLM inference.

Winner — Forge the Future Hackathon 2026 (Elastic × AWS × Sarvam). Team DEFCON1.

---

## The problem

A human reviewer spends roughly 45 minutes on a single insurance claim:
matching CPT/ICD-10/HCPCS codes against patient history, verifying clinical
criteria like step-therapy sequences and drug interactions, cross-referencing
hundreds of payer policy rules, and writing a decision that survives appeal.

It is slow because it is genuinely hard:

- **History is unstructured.** PDFs, scanned notes, lab reports, three date
  formats.
- **Temporal reasoning is subtle.** "PT from 3/15 to 6/20 with a 45-day gap" —
  does that count as continuous therapy?
- **Codes collide.** E10.9 and E11.9 are one character apart and clinically
  different. Semantic search happily blurs them.
- **Drug interactions need real lookup.** A brand name and its generic must
  resolve to the same thing or a contraindication hides.

The usual answer is RAG plus an LLM that summarizes documents so a human can
decide. That does not remove the review, because an LLM can invent a date,
miss a negation, and cannot be held liable for a denial.

## What we built

MediAudit-X inverts the trust model: **the LLM chooses which tools to call, and
the tools produce the facts.** The final APPROVE / DENY / REQUEST_INFO verdict
is computed by a deterministic function over tool results — never written by
the model. If the LLM call fails entirely, a no-LLM tool sweep still completes
the adjudication.

Four grounded tools do the actual work:

| Tool | What it does |
|---|---|
| **Clinical trajectory** | An ES\|QL bi-temporal query (with a DSL aggregation fallback) that computes step-therapy compliance from real encounter history instead of asserting it. |
| **Policy matcher** | RRF hybrid search — BM25 with CPT/ICD field boosts, fused with a dense vector — so exact code matches and reworded clinical language both surface. |
| **Drug interaction auditor** | RxNorm brand/generic resolution against openFDA-flagged pairs, so "Toradol" and "Ketorolac" cannot hide a contraindication. |
| **Audit ledger** | Hash-chained entries (`SHA256(canonical_json(payload) + prev_hash)`), so editing any past decision breaks every subsequent hash. |

Around those sit a document intake pipeline (magic-byte validation, dedup,
size/page limits), an OCR stage (pdfplumber's text layer first, Tesseract for
scanned pages) that writes offset-addressable chunks so every extracted fact
cites back to `(doc_id, page, char_start, char_end)`, a claim-vs-evidence check
that asks whether the documents actually support the submitted codes, and
structured request-correlated logging.

The Next.js dashboard streams the agent's reasoning live over SSE, then shows
the timeline, interaction alerts, and the citation panel behind the verdict.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for how the stages fit together.

---

## Quickstart

Requires an Elasticsearch cluster (Elastic Cloud Serverless or local) and AWS
Bedrock or Anthropic API credentials.

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill in Elastic + AWS/Anthropic credentials
```

Tesseract is a separate binary, needed only for scanned documents:
`apt-get install tesseract-ocr` (Linux), `brew install tesseract` (macOS), or
`winget install UB-Mannheim.TesseractOCR` (Windows).

Create the indices and load the fixtures:

```bash
python -m app.indices.create_indices
python -m app.ingestion.load_sample_data
python -m app.ingestion.load_real_cms_policies
python -m app.ingestion.ingest_synthea_samples   # CLM-2001 .. CLM-2005
```

Run it:

```bash
uvicorn app.main:app --reload --port 8000    # API docs at /docs
python -m pytest tests/ -v                   # needs the steps above first
```

Optionally, if `KIBANA_URL` is set and Agent Builder is enabled on your
project, `python -m app.setup_agent_builder` provisions the claim-chat agent.
Claim chat falls back to the direct Bedrock/Anthropic tool loop without it.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Click into `CLM-1001` and run adjudication — the fixture claim is built to
trigger both the step-therapy denial path and a drug interaction alert.

---

## Project layout

```
backend/app/
  routers/        FastAPI endpoints (claims, intake, ocr, adjudication, chat, audit, patients)
  pipeline/
    ingestion/    upload -> validation -> storage -> claim-files / claim-documents
    ocr/          PENDING documents -> extract + chunk -> document-pages / document-chunks
  agent/          orchestrator.py, the tool-use loop and deterministic _decide()
  tools/          trajectory / policy matcher / drug interaction / audit ledger
  evidence/       claim-vs-evidence check
  actuators/      decision letter + FHIR ClaimResponse
  embeddings/     embed.py, the vector function
  ingestion/      one seed script per data source (sample, CMS LCDs, Synthea)
  indices/        index mappings + names.py constants
  observability/  structured logging, request middleware
frontend/app/     Next.js dashboard, claim detail, new-claim form
data/             sample/ fixtures, synthea_samples/, real CMS LCD policies
```

## Known limitations

- **The embedding is not neural.** `embeddings/embed.py` is deterministic
  feature hashing with TF weighting, chosen so the demo needed no ~1–2 GB model
  download over venue wifi. It captures shared vocabulary, not meaning; RRF
  leans on BM25 for the code precision that actually matters. Swapping in
  `all-mpnet-base-v2` is a one-function change — the `str -> list[float]`
  contract is all the pipeline knows.
- **One temporal probe is implemented,** step-therapy duration. Continuity
  gaps, lab thresholds, and diagnosis-precedes-procedure are specified but not
  built.
- **AWS Textract is configurable but not implemented.** `ocr_provider` selects
  between engines; only `tesseract` has a backend.
- **Policy compilation is manual,** a few hours of clinician time per policy.
  Not scalable past a few dozen without a DSL.
- **Synthea data is clean** in ways real charts are not — no typos, no
  conflicting sources, no retroactive documentation.
- **The benchmark set is small and hand-built.** `eval/run_benchmark.py`
  measures real numbers (see below), but over 9 policy-retrieval cases, 14
  drug-interaction cases, and 12 end-to-end claims that we wrote ourselves.
  Every score is 1.0, which says more about the size of the set than the
  system. No `REQUEST_INFO` case is covered, and the 3 trajectory cases
  execute but return no data. Validation against labelled historical claims
  has not been done.

## Measured so far

`python eval/run_benchmark.py` writes `eval/benchmark_results.json` and
`eval/e2e_benchmark_results.json`. From the last run:

| | Cases | Result |
|---|---|---|
| Policy retrieval | 9 (6 in-domain) | P@1, recall@5, MRR all 1.0 · p50 250 ms |
| Drug interactions | 14 (10 pos, 4 neg) | precision / recall / F1 1.0, no FP or FN · p50 707 ms |
| Trajectory probe | 3 | executes cleanly, but 0 cases returned data |
| End-to-end verdict | 12 | 12/12 correct (5 APPROVED, 7 DENIED) · avg 872 ms |

Read these as sanity checks on a set we built ourselves, not as a benchmark —
see the limitation above.

## Out of scope

Medical necessity judgment, fraud detection, HL7 v2 (FHIR R4 only), and
multi-payer orchestration.

## References

- [RxNorm](https://www.nlm.nih.gov/research/umls/rxnorm/) · [openFDA](https://open.fda.gov/) · [FHIR R4](https://www.hl7.org/fhir/r4/) · [Synthea](https://synthetichealth.github.io/synthea/)
- CMS Local Coverage Determinations (LCD/NCD)

## License

MIT — see [LICENSE](LICENSE).
