"""
Patient history endpoint — supports the frontend Timeline component.
Not in the original API reference table (Section 7), added because the
Timeline UI needs a patient's raw encounter/medication history and there
was no existing route for it.
"""
from fastapi import APIRouter

from app.es_client import get_es_client

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/history")
def get_patient_history(patient_id: str, limit: int = 200):
    es = get_es_client()
    result = es.search(
        index="fhir-clinical-ehr",
        query={"term": {"patient_id": patient_id}},
        sort=[{"timestamp": "asc"}],
        size=limit,
    )
    return [
        {"id": hit["_id"], **hit["_source"]} for hit in result["hits"]["hits"]
    ]
