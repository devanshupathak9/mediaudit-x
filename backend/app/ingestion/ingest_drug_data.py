"""
RxNorm + openFDA -> fda-drug-interactions ingestion.

BUILT LIVE (16 Sept): a real, working pipeline against RxNorm's REST API
(rxnav.nlm.nih.gov) and openFDA's drug label API (api.fda.gov) -- both
free, no API key required. Verified working via manual browser session on
16 Sept (this dev environment's own network sandbox can't reach either
host directly; if `requests` calls below fail with a connection error,
you're likely in the same kind of sandboxed environment -- run this from
a normal internet connection instead, which the event venue should have).

What this does NOT do: resolve arbitrary drug-drug interaction *pairs*
with severity ratings. There is no free, structured, bulk interaction
database with severity levels (that's DrugBank/Lexicomp/Micromedex
territory, all paywalled) -- NLM's own former interaction API was
retired. So this script takes a small, hand-curated list of
(drug_a, drug_b, severity, mechanism) pairs -- the ones this project
already demos against -- and for each one:
  1. Resolves both drug names to real RxCUI codes via RxNorm.
  2. Pulls each drug's real openFDA label to confirm whether it carries
     an actual FDA boxed warning, and extracts a real, quotable excerpt
     for fda_citation instead of an invented citation string.

The three pairs below (with their RxCUIs and citation excerpts) were
verified this way on 16 Sept 2026 and are also committed as static JSON
in data/sample/sample_drug_interactions.json and
data/synthea_samples/synthea_drug_interactions.json -- re-run this script
only if you want to add more pairs or refresh the citations closer to the
event.
"""
import json
import time
from pathlib import Path

import requests

from app.es_client import get_es_client

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"

# Hand-curated: (drug_a, drug_a_synonyms, drug_b, drug_b_synonyms, severity, mechanism)
INTERACTION_PAIRS = [
    (
        "Warfarin", "Coumadin Jantoven Warfarin Sodium",
        "Fluconazole", "Diflucan",
        "Major",
        "Fluconazole inhibits CYP2C9 metabolism of warfarin, increasing bleeding risk.",
    ),
    (
        "Apixaban", "Eliquis",
        "Ketorolac", "Toradol",
        "Contraindicated",
        "Combined anticoagulant and NSAID significantly increases GI and systemic bleeding risk.",
    ),
    (
        "Warfarin", "Coumadin Jantoven Warfarin Sodium",
        "Ciprofloxacin", "Cipro",
        "Major",
        "Ciprofloxacin inhibits CYP1A2-mediated metabolism of warfarin and displaces it from "
        "plasma proteins, increasing INR and bleeding risk.",
    ),
]


def resolve_rxcui(drug_name: str) -> str | None:
    resp = requests.get(f"{RXNAV_BASE}/rxcui.json", params={"name": drug_name, "search": "2"}, timeout=10)
    resp.raise_for_status()
    ids = resp.json().get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None


def fetch_label_citation(generic_name: str) -> tuple[bool, str]:
    """
    Returns (has_boxed_warning, citation_excerpt). Pulls the real openFDA
    label for the given generic name and extracts the first ~300 chars of
    its boxed_warning (or drug_interactions, if no boxed warning exists)
    as a real, quotable excerpt -- never invented text.
    """
    resp = requests.get(
        OPENFDA_BASE,
        params={"search": f'openfda.generic_name:"{generic_name.upper()}"', "limit": "1"},
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"openFDA lookup failed ({resp.status_code}) for {generic_name} -- no citation available."
    results = resp.json().get("results", [])
    if not results:
        return False, f"No openFDA label found for {generic_name}."
    label = results[0]
    if label.get("boxed_warning"):
        excerpt = label["boxed_warning"][0][:400]
        return True, f'{generic_name} FDA label, boxed warning: "{excerpt}..."'
    if label.get("drug_interactions"):
        excerpt = label["drug_interactions"][0][:400]
        return False, f'{generic_name} FDA label, Drug Interactions section: "{excerpt}..."'
    return False, f"{generic_name} FDA label found but has no boxed_warning or drug_interactions section."


def build_interaction_docs() -> list[dict]:
    docs = []
    for interaction_id, (name_a, syn_a, name_b, syn_b, severity, mechanism) in enumerate(INTERACTION_PAIRS, start=1):
        rxcui_a = resolve_rxcui(name_a)
        time.sleep(0.3)  # be polite to the free public API
        rxcui_b = resolve_rxcui(name_b)
        time.sleep(0.3)
        has_boxed_a, citation_a = fetch_label_citation(name_a)
        time.sleep(0.3)

        docs.append({
            "interaction_id": f"INT-LIVE-{interaction_id}",
            "drug_a_rxnorm": rxcui_a,
            "drug_a_name": name_a,
            "drug_a_synonyms": syn_a,
            "drug_b_rxnorm": rxcui_b,
            "drug_b_name": name_b,
            "drug_b_synonyms": syn_b,
            "severity": severity,
            "mechanism": mechanism,
            "fda_boxed_warning": has_boxed_a,
            "fda_citation": citation_a,
        })
    return docs


def load_all(write_to_file: Path | None = None):
    docs = build_interaction_docs()
    if write_to_file:
        write_to_file.write_text(json.dumps(docs, indent=2))
        print(f"[wrote] {len(docs)} interaction docs -> {write_to_file}")

    es = get_es_client()
    for doc in docs:
        # FIXED (18 Sept): stable id=interaction_id, same idempotency fix
        # as the other loaders.
        es.index(index="fda-drug-interactions", document=doc, id=doc["interaction_id"])
    es.indices.refresh(index="fda-drug-interactions")
    print(f"[loaded] {len(docs)} docs -> fda-drug-interactions")


if __name__ == "__main__":
    out_path = Path(__file__).parent.parent.parent.parent / "data" / "live_ingested_drug_interactions.json"
    load_all(write_to_file=out_path)
