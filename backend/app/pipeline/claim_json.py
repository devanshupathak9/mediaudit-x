"""
The structured claim the insurer receives: a FHIR R4 `Claim` resource,
built when a claim is submitted (persist_claim_draft) and stored on the
claim record as `fhir_claim`. GET /claims/{id}/claim-json serves it.

Built only from fields already on the claim -- identifiers and payer
from intake, codes/medications from the draft (each with the text span it
was extracted from), amount/dates/hospital from the hospital's form. Nothing
here is inferred: a field the claim doesn't have is left out, not filled
with a default.

Each diagnosis/item/medication carries a `source-citation` extension
(doc id, page, quoted text) so the insurer can trace every code back to
the document -- or to the hospital form, doc_id "hospital-form" -- it came
from. Extensions are the FHIR-sanctioned way to add this; the resource
stays valid R4.
"""
from datetime import datetime, timezone

ICD10CM_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
CPT_SYSTEM = "http://www.ama-assn.org/go/cpt"
RXNORM_SYSTEM = "http://www.nlm.nih.gov/research/umls/rxnorm"
CLAIM_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type"
INFO_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/claiminformationcategory"
PRIORITY_SYSTEM = "http://terminology.hl7.org/CodeSystem/processpriority"
CITATION_EXTENSION_URL = "https://mediaudit-x.dev/fhir/StructureDefinition/source-citation"

FHIR_CLAIM_TYPES = {"institutional", "oral", "pharmacy", "professional", "vision"}


def _citation(entry: dict) -> list[dict]:
    if not entry.get("cited_text"):
        return []
    return [{
        "url": CITATION_EXTENSION_URL,
        "extension": [
            {"url": "docId", "valueString": str(entry.get("doc_id") or "")},
            {"url": "page", "valueInteger": int(entry.get("page_number") or 0)},
            {"url": "quote", "valueString": entry["cited_text"]},
        ],
    }]


def _coding(system: str, code: str, display: str | None) -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return coding


def _ordered(entries: list[dict], primary_code: str | None) -> list[dict]:
    """Primary code first (it's what adjudication uses), then the rest,
    each code once."""
    seen, ordered = set(), []
    primary = [e for e in entries if e.get("code") == primary_code]
    for entry in primary + entries:
        code = entry.get("code")
        if code and code not in seen:
            seen.add(code)
            ordered.append(entry)
    if primary_code and primary_code not in seen:
        ordered.insert(0, {"code": primary_code})
    return ordered


def build_fhir_claim(claim: dict) -> dict:
    details = claim.get("details") or {}
    admission = details.get("admission") or {}
    hospital = details.get("hospital") or {}
    insurance = details.get("insurance") or {}
    patient = details.get("patient") or {}

    resource: dict = {
        "resourceType": "Claim",
        "id": claim["claim_id"],
        "identifier": [{"system": "urn:mediaudit-x:claim-id", "value": claim["claim_id"]}],
        "status": "active",
        "use": "claim",
        "created": claim.get("submitted_date") or datetime.now(timezone.utc).isoformat(),
        "priority": {"coding": [{"system": PRIORITY_SYSTEM, "code": "normal"}]},
    }

    claim_type = claim.get("claim_type")
    if claim_type in FHIR_CLAIM_TYPES:
        resource["type"] = {"coding": [{"system": CLAIM_TYPE_SYSTEM, "code": claim_type}]}

    if claim.get("patient_id"):
        resource["patient"] = {"reference": f"Patient/{claim['patient_id']}"}
        if patient.get("name"):
            resource["patient"]["display"] = patient["name"]

    if claim.get("payer_name"):
        resource["insurer"] = {"display": claim["payer_name"]}
        coverage = {"display": claim["payer_name"]}
        if insurance.get("policy_number"):
            coverage["identifier"] = {"value": insurance["policy_number"]}
        resource["insurance"] = [{"sequence": 1, "focal": True, "coverage": coverage}]

    provider = hospital.get("name") or claim.get("submitted_by")
    if provider and provider != "unknown":
        resource["provider"] = {"display": provider}

    diagnoses = _ordered(claim.get("extracted_diagnoses") or [], claim.get("icd10_code"))
    if diagnoses:
        resource["diagnosis"] = [
            {
                "sequence": i,
                "diagnosisCodeableConcept": {"coding": [_coding(ICD10CM_SYSTEM, d["code"], d.get("description"))]},
                **({"extension": _citation(d)} if _citation(d) else {}),
            }
            for i, d in enumerate(diagnoses, start=1)
        ]

    period = {k: v for k, v in (("start", admission.get("admission_date")), ("end", admission.get("discharge_date"))) if v}
    procedures = _ordered(claim.get("extracted_procedures") or [], claim.get("cpt_code"))
    if procedures:
        resource["item"] = []
        for i, p in enumerate(procedures, start=1):
            item = {
                "sequence": i,
                "productOrService": {"coding": [_coding(CPT_SYSTEM, p["code"], p.get("description"))]},
            }
            if diagnoses:
                item["diagnosisSequence"] = [1]
            if period:
                item["servicedPeriod"] = period
            if _citation(p):
                item["extension"] = _citation(p)
            resource["item"].append(item)

    supporting = []
    for med in claim.get("extracted_medications") or []:
        info = {
            "sequence": len(supporting) + 1,
            "category": {"coding": [{"system": INFO_CATEGORY_SYSTEM, "code": "info"}], "text": "medication"},
            "code": {"text": med.get("name")},
        }
        if med.get("rxnorm_code"):
            info["code"]["coding"] = [_coding(RXNORM_SYSTEM, med["rxnorm_code"], med.get("name"))]
        if _citation(med):
            info["extension"] = _citation(med)
        supporting.append(info)
    for doc in claim.get("attached_documents") or []:
        supporting.append({
            "sequence": len(supporting) + 1,
            "category": {"coding": [{"system": INFO_CATEGORY_SYSTEM, "code": "attachment"}]},
            "valueAttachment": {"url": doc.get("source_uri"), "title": f"{doc.get('doc_type')} {doc.get('doc_id')}"},
        })
    if supporting:
        resource["supportingInfo"] = supporting

    if claim.get("claim_amount"):
        resource["total"] = {"value": claim["claim_amount"], "currency": "USD"}

    return resource
