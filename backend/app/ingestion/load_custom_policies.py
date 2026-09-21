"""
Generic loader for adding a new set of payer policies to the
medical-policies index -- same idempotent create-or-update pattern as
load_real_cms_policies.py / ingest_policies.py, generalized to any JSON
file that already matches the medical_policies.json mapping shape.

Each input doc needs at minimum: policy_id, payer_name, title, cpt_codes,
icd10_codes, clinical_indications, contraindications, step_therapy_required.
An optional "_source_note" field documents provenance (real source or
hand-built/illustrative) and is stripped before indexing, not stored.

Usage:
    python -m app.ingestion.load_custom_policies data/my_new_policies.json
    python -m app.ingestion.load_custom_policies data/my_new_policies.json --dry-run
"""
import json
import sys
from pathlib import Path

from app.es_client import get_es_client
from app.embeddings.embed import embed_text


def _strip_provenance_fields(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def load_all(json_path: Path, dry_run: bool = False):
    docs = json.loads(json_path.read_text())
    es = None if dry_run else get_es_client()

    for raw_doc in docs:
        note = raw_doc.get("_source_note", "")
        doc = _strip_provenance_fields(raw_doc)
        doc["policy_vector"] = embed_text(f"{doc['title']} {doc['clinical_indications']}")

        print(f"--- {doc['policy_id']}: {doc['title']} (payer: {doc['payer_name']}, CPT {doc['cpt_codes']}) ---")
        print(f"step_therapy_required: {doc['step_therapy_required']}")
        if note:
            print(f"source: {note[:200]}...")

        if not dry_run:
            # id=policy_id makes this safe to re-run -- reruns update the
            # same document instead of creating duplicates.
            es.index(index="medical-policies", document=doc, id=doc["policy_id"])

    if not dry_run:
        es.indices.refresh(index="medical-policies")
        print(f"\n[loaded] {len(docs)} polic{'y' if len(docs) == 1 else 'ies'} -> medical-policies")
    else:
        print(f"\n[dry run] {len(docs)} doc(s) parsed OK, nothing written")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python -m app.ingestion.load_custom_policies <path-to-policies.json> [--dry-run]")
        sys.exit(1)
    load_all(Path(args[0]), dry_run="--dry-run" in sys.argv)
