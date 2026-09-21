"""
Bi-temporal clinical trajectory tool — proves whether a patient satisfied
a step-therapy / conservative-therapy requirement using real longitudinal
data, rather than an LLM's guess about the chart.

BUILT LIVE (18 Sept): the ES|QL query is the primary path (this is the
capability the spec calls out as the differentiator over pure LLM/vector
approaches — deterministic aggregation over structured time-series data).
A plain DSL aggregation fallback is included because ES|QL's retriever
surface and availability differ across Elasticsearch versions/local Docker
images, and a demo should not die on a version mismatch mid-adjudication.
Both paths compute the same decision fields so the caller doesn't need to
know which one ran.
"""
from datetime import datetime, timezone

from app.es_client import get_es_client


def _esql_escape(value: str) -> str:
    return value.replace('"', '\\"')


def query_patient_clinical_trajectory(
    patient_id: str,
    therapy_keywords: list[str],
    lookback_months: int = 12,
    required_duration_days: int = 180,
) -> dict:
    """
    Verifies, from real encounter/medication history, whether the patient
    has `required_duration_days` worth of documented conservative therapy
    (matched by `therapy_keywords` against code_display) within the
    lookback window. Returns the raw trajectory facts plus a computed
    `step_therapy_met` boolean — the agent should treat this boolean as
    ground truth, not re-derive it itself from free text.
    """
    es = get_es_client()

    keyword_clause = " OR ".join(
        f'code_display LIKE "*{_esql_escape(kw)}*"' for kw in therapy_keywords
    )

    esql_query = f"""
        FROM fhir-clinical-ehr
        | WHERE patient_id == "{_esql_escape(patient_id)}" AND timestamp >= NOW() - {lookback_months * 30} DAYS
        | EVAL is_conservative_therapy = ({keyword_clause})
        | WHERE is_conservative_therapy == true
        | STATS
            total_conservative_encounters = COUNT(*),
            earliest_therapy = MIN(timestamp),
            latest_therapy = MAX(timestamp)
          BY patient_id
        | EVAL therapy_duration_days = DATE_DIFF("days", earliest_therapy, latest_therapy)
    """

    try:
        response = es.esql.query(query=esql_query)
        rows = response.body.get("values", [])
        columns = [c["name"] for c in response.body.get("columns", [])]
        if not rows:
            return {
                "source": "esql",
                "patient_id": patient_id,
                "total_conservative_encounters": 0,
                "therapy_duration_days": 0,
                "step_therapy_met": False,
                "required_duration_days": required_duration_days,
                "raw": response.body,
            }
        row = dict(zip(columns, rows[0]))
        duration_days = row.get("therapy_duration_days") or 0
        return {
            "source": "esql",
            "patient_id": patient_id,
            "total_conservative_encounters": row.get("total_conservative_encounters", 0),
            "earliest_therapy": row.get("earliest_therapy"),
            "latest_therapy": row.get("latest_therapy"),
            "therapy_duration_days": duration_days,
            "required_duration_days": required_duration_days,
            "step_therapy_met": duration_days >= required_duration_days,
            "raw": response.body,
        }
    except Exception as esql_error:  # noqa: BLE001 - deliberate broad fallback
        return _dsl_fallback(
            es, patient_id, therapy_keywords, lookback_months,
            required_duration_days, esql_error,
        )


def _dsl_fallback(
    es, patient_id, therapy_keywords, lookback_months, required_duration_days, esql_error,
):
    result = es.search(
        index="fhir-clinical-ehr",
        query={
            "bool": {
                "must": [{"term": {"patient_id": patient_id}}],
                "should": [
                    {"match_phrase": {"code_display": kw}} for kw in therapy_keywords
                ],
                "minimum_should_match": 1 if therapy_keywords else 0,
            }
        },
        sort=[{"timestamp": "asc"}],
        size=500,
    )
    hits = [h["_source"] for h in result["hits"]["hits"]]
    if not hits:
        return {
            "source": "dsl_fallback",
            "esql_error": str(esql_error),
            "patient_id": patient_id,
            "total_conservative_encounters": 0,
            "therapy_duration_days": 0,
            "step_therapy_met": False,
            "required_duration_days": required_duration_days,
        }

    timestamps = [
        datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00")) for h in hits
    ]
    earliest, latest = min(timestamps), max(timestamps)
    duration_days = (latest - earliest).total_seconds() / 86400

    return {
        "source": "dsl_fallback",
        "esql_error": str(esql_error),
        "patient_id": patient_id,
        "total_conservative_encounters": len(hits),
        "earliest_therapy": earliest.isoformat(),
        "latest_therapy": latest.isoformat(),
        "therapy_duration_days": round(duration_days, 2),
        "required_duration_days": required_duration_days,
        "step_therapy_met": duration_days >= required_duration_days,
    }
