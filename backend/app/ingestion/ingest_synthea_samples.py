"""
Loads the real Synthea-derived fixtures in data/synthea_samples/ (as
opposed to the hand-built ones in data/sample/) into Elasticsearch.

BUILT LIVE (16 Sept): these three files were produced by actually running
the Synthea CLI (population 150, ages 50-85, Massachusetts, seed 42),
scanning the output for a patient with a real knee-osteoarthritis
diagnosis and a patient with a real, verified Warfarin + Ciprofloxacin
prescription overlap, then running parse_synthea.py (fixed against the
real bundle structure) against just those two patients' bundles. See
each file's `_source_note` field (present on the claims for provenance;
stripped before indexing here since it's not part of the ES schema) for
exactly what's real and what's authored on top of it.

Run with: python -m app.ingestion.ingest_synthea_samples
"""
import json
from pathlib import Path

from app.es_client import get_es_client
from app.embeddings.embed import embed_text

SAMPLE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "synthea_samples"

FILE_TO_INDEX = {
    "synthea_fhir_encounters.json": "fhir-clinical-ehr",
    "synthea_claims.json": "insurance-claims",
    "synthea_drug_interactions.json": "fda-drug-interactions",
}

# FIXED (18 Sept): same idempotency fix as load_sample_data.py -- see
# that file's comment. Without a stable id, re-running this script after
# an earlier partial failure (e.g. the dot_product zero-vector bug this
# script hit mid-run on 18 Sept) duplicates whatever it already
# successfully indexed before the crash.
INDEX_TO_ID_FIELD = {
    "fhir-clinical-ehr": "encounter_id",
    "insurance-claims": "claim_id",
    "fda-drug-interactions": "interaction_id",
}


def _strip_provenance_fields(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _backfill_vector(index: str, doc: dict) -> dict:
    if index == "fhir-clinical-ehr":
        text = " ".join(filter(None, [doc.get("code_display"), doc.get("clinician_notes")]))
        vector = embed_text(text)
        # dot_product fields reject the all-zero vector embed_text returns
        # for empty text; leave the field out for those docs instead.
        if any(vector):
            doc["notes_vector"] = vector
    return doc


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
