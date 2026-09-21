"""
Loads data/real_cms_lcd_policies.json into the medical-policies index.

WHERE THIS DATA CAME FROM: the user downloaded CMS's own "current LCD"
bulk database export directly from the Medicare Coverage Database
(cms.gov/medicare-coverage-database -> Downloadable Databases) -- a zip
containing the full national LCD table (lcd.csv, ~220k LCD revision rows)
plus contractor/jurisdiction cross-reference tables. This sidesteps the
Akamai bot-protection that blocked automated fetches from cms.gov
directly (see ingest_policies.py's docstring) -- a human downloading the
file through their own browser has no such restriction.

app/ingestion/extract_real_cms_lcds.py (this pair script) then:
  - found LCD L36575 "Total Knee Arthroplasty" (CPT 27447, matches
    CLM-1001/CLM-2001) and LCD L34163 "Total Hip Arthroplasty" (CPT
    27130), both status=A (currently active)
  - stripped the embedded HTML from CMS's own `indication` field
  - split that field on its own real "Limitations" heading into
    clinical_indications / contraindications (mirrors what
    ingest_policies.py does for a PDF, but here the source is already
    structured CSV, not heuristic PDF text extraction)
  - resolved the adopting Medicare Administrative Contractor's real
    name via the contractor cross-reference tables (Noridian Healthcare
    Solutions, LLC, for both)
  - deliberately left icd10_codes blank: this CSV table does not carry
    ICD-10 codes (CMS ships those in a separate "billing and coding
    article" export this download didn't include) -- left empty rather
    than guessed

Each doc's `_source_note` (stripped before indexing, same convention as
ingest_synthea_samples.py) documents the exact LCD ID, revision date,
and adopting contractor for anyone who wants to check it against the
source themselves.

FINDING WORTH KNOWING FOR THE DEMO: unlike the hand-authored sample
policy (POL-UHC-KNEE-01, which specifies "6 months of physical
therapy"), the real Medicare LCD does NOT specify a fixed therapy
duration -- it says "history of unsuccessful conservative therapy...
clearly addressed in the pre-procedure medical record" without a month
count. So step_therapy_required computed out to False for both real
LCDs. That's accurate to the real policy, not a bug -- Medicare's
national LCD is less prescriptive than commercial payer policy on this
point, and the demo narrative should say so if it uses these documents.

Run with: python -m app.ingestion.load_real_cms_policies
"""
import json
from pathlib import Path

from app.es_client import get_es_client
from app.embeddings.embed import embed_text

DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "real_cms_lcd_policies.json"


def _strip_provenance_fields(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def load_all(dry_run: bool = False):
    docs = json.loads(DATA_PATH.read_text())
    es = None if dry_run else get_es_client()

    for raw_doc in docs:
        note = raw_doc.get("_source_note", "")
        doc = _strip_provenance_fields(raw_doc)
        doc["policy_vector"] = embed_text(f"{doc['title']} {doc['clinical_indications']}")

        print(f"--- {doc['policy_id']}: {doc['title']} (CPT {doc['cpt_codes']}) ---")
        print(f"step_therapy_required: {doc['step_therapy_required']}")
        print(f"source: {note[:200]}...")

        if not dry_run:
            # FIXED (18 Sept): stable id=policy_id, same idempotency fix
            # as load_sample_data.py / ingest_synthea_samples.py.
            es.index(index="medical-policies", document=doc, id=doc["policy_id"])

    if not dry_run:
        es.indices.refresh(index="medical-policies")
        print(f"\n[loaded] {len(docs)} real CMS LCD policies -> medical-policies")
    else:
        print(f"\n[dry run] {len(docs)} docs parsed OK, nothing written")


if __name__ == "__main__":
    import sys
    load_all(dry_run="--dry-run" in sys.argv)
