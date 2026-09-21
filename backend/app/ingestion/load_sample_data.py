"""
Loads the small hand-built fixture set from data/sample/ into Elasticsearch.
Useful for testing queries end-to-end before you have real Synthea output.

BUILT LIVE (18 Sept): now backfills notes_vector / policy_vector via the
real embed_text() before indexing, since the tools no longer accept an
all-zero placeholder vector as meaningful input.

Run with: python -m app.ingestion.load_sample_data
"""
import json
from pathlib import Path

from app.es_client import get_es_client
from app.embeddings.embed import embed_text

SAMPLE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "sample"

FILE_TO_INDEX = {
    "sample_claims.json": "insurance-claims",
    "sample_fhir_encounters.json": "fhir-clinical-ehr",
    "sample_policies.json": "medical-policies",
    "sample_drug_interactions.json": "fda-drug-interactions",
}

# FIXED (18 Sept): es.index() with no explicit id creates a brand-new
# document on every call, so re-running this script (e.g. after fixing a
# bug partway through a load) silently duplicates every fixture instead
# of upserting it -- caught when a duplicated Apixaban/Ketorolac
# interaction made test_drug_interaction_catches_brand_generic_mismatch
# return 2 hits instead of 1. Indexing with id=<natural key> makes this
# script idempotent/safe-to-rerun, matching create_indices.py's own
# "safe to re-run" convention.
INDEX_TO_ID_FIELD = {
    "insurance-claims": "claim_id",
    "fhir-clinical-ehr": "encounter_id",
    "medical-policies": "policy_id",
    "fda-drug-interactions": "interaction_id",
}


def _backfill_vector(index: str, doc: dict) -> dict:
    if index == "fhir-clinical-ehr":
        text = " ".join(filter(None, [doc.get("code_display"), doc.get("clinician_notes")]))
        vector = embed_text(text)
        # dot_product fields reject the all-zero vector embed_text returns
        # for empty text; leave the field out for those docs instead.
        if any(vector):
            doc["notes_vector"] = vector
    elif index == "medical-policies":
        text = " ".join(filter(None, [
            doc.get("title"), doc.get("clinical_indications"), doc.get("contraindications"),
        ]))
        doc["policy_vector"] = embed_text(text)
    return doc


def _strip_provenance_fields(doc: dict) -> dict:
    """Drops any _source_note / _-prefixed provenance fields before
    indexing -- same convention as ingest_synthea_samples.py. Several
    sample_*.json fixtures added 18 Sept carry a _source_note explaining
    why that fixture exists / what it's meant to demonstrate; it's for
    humans reading the JSON file, not part of the ES schema."""
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def load_all():
    es = get_es_client()
    for filename, index in FILE_TO_INDEX.items():
        path = SAMPLE_DIR / filename
        if not path.exists():
            print(f"[skip] {filename} not found")
            continue
        docs = json.loads(path.read_text())
        id_field = INDEX_TO_ID_FIELD.get(index)
        for doc in docs:
            doc = _strip_provenance_fields(doc)
            doc = _backfill_vector(index, doc)
            doc_id = doc.get(id_field) if id_field else None
            es.index(index=index, document=doc, id=doc_id)
        print(f"[loaded] {len(docs)} docs -> {index}")
    es.indices.refresh(index=",".join(FILE_TO_INDEX.values()))
    print("[refreshed] all indices — data is immediately searchable")


if __name__ == "__main__":
    load_all()
