"""
FHIR bundle -> flat document parser, matching the fhir-clinical-ehr schema.

BUILT LIVE (16 Sept), fixed against REAL Synthea output (not guessed):
inspected actual generated bundles and found the original stub's field
paths were wrong for two of the four resource types —
MedicationRequest's code lives under `medicationCodeableConcept.coding`,
not `code.coding`, and Encounter's code lives under `type[0].coding`, not
`code.coding`. Condition matched the stub's default already. Subject
references also need the `urn:uuid:` prefix stripped since Synthea's
default bundle export uses UUID-only urn references, not `Patient/<id>`.

Real Synthea output generally does NOT include free-text clinician notes
on these four resource types (that lives in DocumentReference C-CDA
attachments, which this doesn't parse) — clinician_notes is left empty
for real parsed data rather than fabricated, unlike the hand-built
data/sample/ fixtures which do include invented narrative text for demo
readability.
"""
import json
from pathlib import Path


def _strip_ref(reference: str | None) -> str | None:
    if not reference:
        return None
    return reference.split("urn:uuid:")[-1].split("/")[-1]


def _first_coding(codeable_concept: dict | None) -> dict:
    if not codeable_concept:
        return {}
    coding = codeable_concept.get("coding", [])
    return coding[0] if coding else {}


def _resource_code_display(resource: dict, resource_type: str) -> tuple[str | None, str | None]:
    if resource_type == "MedicationRequest":
        coding = _first_coding(resource.get("medicationCodeableConcept"))
    elif resource_type == "Encounter":
        types = resource.get("type", [])
        coding = _first_coding(types[0]) if types else {}
    else:  # Condition, Observation
        coding = _first_coding(resource.get("code"))
    return coding.get("code"), coding.get("display")


def _resource_timestamp(resource: dict, resource_type: str) -> str | None:
    if resource_type == "Encounter":
        return resource.get("period", {}).get("start")
    if resource_type == "MedicationRequest":
        return resource.get("authoredOn")
    if resource_type == "Condition":
        return resource.get("onsetDateTime") or resource.get("recordedDate")
    if resource_type == "Observation":
        return resource.get("effectiveDateTime")
    return None


def _dosage_text(resource: dict) -> str | None:
    instructions = resource.get("dosageInstruction", [])
    if not instructions:
        return None
    return instructions[0].get("text")


def _lab_value(resource: dict) -> float | None:
    value = resource.get("valueQuantity", {}).get("value")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_bundle(bundle_path: Path) -> list[dict]:
    """
    Flattens one Synthea FHIR bundle's Encounter/MedicationRequest/
    Condition/Observation resources into fhir-clinical-ehr-shaped docs.
    Vector backfill (notes_vector) happens at ingest time, not here —
    see ingest scripts, matching how load_sample_data.py does it.
    """
    bundle = json.loads(bundle_path.read_text())
    documents = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")

        if resource_type not in ("Encounter", "MedicationRequest", "Condition", "Observation"):
            continue

        code, code_display = _resource_code_display(resource, resource_type)
        subject_ref = resource.get("subject", {}).get("reference")

        doc = {
            "patient_id": _strip_ref(subject_ref),
            "encounter_id": resource.get("id"),
            "timestamp": _resource_timestamp(resource, resource_type),
            "resource_type": resource_type,
            "clinical_status": (
                resource.get("status")
                or resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code")
            ),
            "code": code,
            "code_display": code_display,
            "dosage": _dosage_text(resource) if resource_type == "MedicationRequest" else None,
            "clinician_notes": None,  # not present in default Synthea export — see module docstring
            "lab_result_numeric": _lab_value(resource) if resource_type == "Observation" else None,
        }
        if doc["timestamp"] is None:
            continue  # skip anything we can't place on the timeline
        documents.append(doc)

    return documents


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m app.ingestion.parse_synthea <path_to_bundle.json>")
        sys.exit(1)

    docs = parse_bundle(Path(sys.argv[1]))
    print(f"Parsed {len(docs)} documents:")
    for d in docs[:5]:
        print(json.dumps(d, indent=2))
