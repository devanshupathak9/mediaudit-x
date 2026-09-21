"""
Deterministic FDA contraindication / interaction auditor.

BUILT LIVE (18 Sept): added resolve_medication_to_rxnorm() so the tool
works from clinical free text (brand OR generic names) rather than
requiring pre-resolved RxNorm codes as input. This is what makes the
"demo killer moment" real: a new prescription entered as "Toradol"
resolves via drug_b_synonyms to the same interaction record as
"Ketorolac" would, catching the Eliquis (Apixaban) interaction that a
pure vector search would risk missing (the two drug names are lexically
and semantically distant — Toradol/Ketorolac only share a link through
the synonym field populated during ingestion, which is exactly the BM25
"exact match on the right field" behavior this project argues for over
embedding-only retrieval).
"""
from app.es_client import get_es_client


def resolve_medication_to_rxnorm(name: str) -> str | None:
    """
    Resolve a brand or generic drug name to its RxNorm code by searching
    both the canonical name and synonym fields. Returns None if nothing
    matches closely enough to trust.
    """
    es = get_es_client()
    response = es.search(
        index="fda-drug-interactions",
        query={
            "bool": {
                "should": [
                    {"match": {"drug_a_name": name}},
                    {"match": {"drug_a_synonyms": name}},
                    {"match": {"drug_b_name": name}},
                    {"match": {"drug_b_synonyms": name}},
                ]
            }
        },
        size=1,
    )
    hits = response["hits"]["hits"]
    if not hits:
        return None
    source = hits[0]["_source"]
    name_lower = name.strip().lower()
    for side in ("a", "b"):
        candidate_name = source.get(f"drug_{side}_name", "").lower()
        candidate_synonyms = source.get(f"drug_{side}_synonyms", "").lower()
        if name_lower in candidate_name or name_lower in candidate_synonyms:
            return source.get(f"drug_{side}_rxnorm")
    # fall back to whichever side matched at all
    return source.get("drug_a_rxnorm")


def audit_drug_drug_contraindications(
    active_rxnorm_codes: list[str],
    new_medication_code: str,
) -> dict:
    """
    active_rxnorm_codes / new_medication_code may be either already-resolved
    RxNorm codes or raw drug names — names are resolved via
    resolve_medication_to_rxnorm() first so callers (including the agent,
    which sees free-text medication names in clinical notes) don't need to
    do their own RxNorm lookups.
    """
    resolved_active = [
        resolve_medication_to_rxnorm(code) or code for code in active_rxnorm_codes
    ]
    resolved_new = resolve_medication_to_rxnorm(new_medication_code) or new_medication_code

    es = get_es_client()
    response = es.search(
        index="fda-drug-interactions",
        query={
            "bool": {
                "should": [
                    {
                        "bool": {
                            "must": [
                                {"terms": {"drug_a_rxnorm": resolved_active}},
                                {"term": {"drug_b_rxnorm": resolved_new}},
                            ]
                        }
                    },
                    {
                        "bool": {
                            "must": [
                                {"term": {"drug_a_rxnorm": resolved_new}},
                                {"terms": {"drug_b_rxnorm": resolved_active}},
                            ]
                        }
                    },
                ]
            }
        },
    )
    body = response.body
    body["_resolved"] = {
        "active_rxnorm_codes": resolved_active,
        "new_medication_code": resolved_new,
    }
    return body
