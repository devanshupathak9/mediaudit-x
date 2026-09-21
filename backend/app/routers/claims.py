"""
Claim intake endpoints.

BUILT LIVE (17 Sept): adds real claim creation + document upload on top of
the existing read-only CRUD. Before this, claims only entered the system
through the offline ingestion scripts (load_sample_data.py,
ingest_synthea_samples.py) -- there was no user-facing way to get a new
claim into insurance-claims. The frontend's "Upload Claim" quick action
pointed nowhere (labeled "coming soon", not wired to anything).

Design notes:
- POST /claims creates a real document in the insurance-claims index with
  status=PENDING, ready to be adjudicated through the existing
  POST /claims/{claim_id}/adjudicate flow -- no separate "upload" data
  path, this feeds the same pipeline everything else already uses.
- Claims created by document upload live in claim-files, not here;
  list/get read both indices (see app/indices/names.py).
- Document upload moved to routers/intake.py (backed by
  app.pipeline.ingestion), which validates files before storing them and
  also serves POST /claims/{claim_id}/documents.
- Elasticsearch documents here are indexed without an explicit id, same
  as every ingestion script in this repo (see their `es.index(...)`
  calls) -- the app's own claim_id is the identity clients use; the
  ES-internal _id is an implementation detail this router looks up by
  searching on claim_id, same pattern list_claims/get_claim already use.
"""
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS, INSURANCE_CLAIMS
from app.pipeline.ingestion.models import CLAIM_ID_PATTERN
from app.tools.audit_ledger import append_event

router = APIRouter(prefix="/claims", tags=["claims"])


class ClaimCreate(BaseModel):
    patient_id: str
    payer_name: str
    cpt_code: str
    icd10_code: str
    claim_amount: float = Field(gt=0)
    claim_type: str = "professional"
    # auto-generated if not supplied; restricted so it is safe as a
    # storage path segment for uploaded documents
    claim_id: str | None = Field(default=None, pattern=CLAIM_ID_PATTERN)


class ReviewerDecision(BaseModel):
    """
    A human reviewer's final call on a claim -- distinct from the AI
    agent's recommendation in adjudication-results. The two are kept as
    separate records (see submit_reviewer_decision below) so the audit
    trail shows both what the agent suggested and what a person actually
    decided, even when they disagree.
    """
    decision: Literal["APPROVE", "DENY", "REQUEST_INFO"]
    reviewer_comment: str = Field(min_length=1)
    reviewer_name: str = "Insurance Reviewer"


_DECISION_TO_STATUS = {"APPROVE": "APPROVED", "DENY": "DENIED", "REQUEST_INFO": "REQUEST_INFO"}


def _find_claim(es, claim_id: str) -> dict:
    """Returns the raw ES hit ({"_id": ..., "_source": {...}}) or raises 404."""
    result = es.search(
        index=ALL_CLAIMS,
        query={"term": {"claim_id": claim_id}},
        size=1,
        ignore_unavailable=True,
    )
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="Claim not found")
    return hits[0]


@router.get("")
def list_claims(limit: int = 20):
    es = get_es_client()
    # Both uploaded (claim-files) and manual/sample (insurance-claims)
    # claims, newest first so fresh uploads show at the top.
    result = es.search(
        index=ALL_CLAIMS,
        query={"match_all": {}},
        sort=[{"submitted_date": {"order": "desc", "unmapped_type": "date"}}],
        size=limit,
        ignore_unavailable=True,
    )
    return [
        {"id": hit["_id"], "index": hit["_index"], **hit["_source"]} for hit in result["hits"]["hits"]
    ]


@router.get("/{claim_id}")
def get_claim(claim_id: str):
    es = get_es_client()
    hit = _find_claim(es, claim_id)
    return {"id": hit["_id"], "index": hit["_index"], **hit["_source"]}


@router.get("/{claim_id}/claim-json")
def get_claim_json(claim_id: str):
    """The structured claim sent to the insurer: a FHIR R4 Claim, built when
    the claim is submitted (see app/pipeline/claim_json.py). 404 until the
    claim's codes have been extracted and it has been submitted."""
    es = get_es_client()
    hit = _find_claim(es, claim_id)
    fhir_claim = hit["_source"].get("fhir_claim")
    if not fhir_claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} has no structured claim yet (status {hit['_source'].get('status')}); "
                   "it is built once codes are extracted from the documents and the claim is submitted.",
        )
    return fhir_claim


@router.get("/{claim_id}/adjudications")
def get_latest_adjudication(claim_id: str):
    """
    ADDED (18 Sept): the frontend previously only ever saw an adjudication
    result via the live SSE stream from POST /{claim_id}/adjudicate,
    stored in React state -- nothing persisted it for a page reload or a
    later visit, so a claim that was adjudicated an hour ago looked
    exactly like one that was never touched. This returns the most recent
    adjudication-results document for the claim (or 404 if none exists
    yet) so the frontend can pre-populate the Overview/Adjudication/Audit
    Trail tabs on load instead of showing them permanently blank after a
    refresh. Shape matches the "done" SSE event's data exactly, so the
    same frontend rendering code works for both a live run and a
    page-load restore.
    """
    es = get_es_client()
    result = es.search(
        index="adjudication-results",
        query={"term": {"claim_id": claim_id}},
        sort=[{"decided_at": "desc"}],
        size=1,
    )
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="No adjudication has been run for this claim yet")
    doc = hits[0]["_source"]

    ledger_result = es.search(
        index="audit-ledger",
        query={"term": {"adjudication_id": doc.get("adjudication_id")}},
        size=1,
    )
    ledger_hits = ledger_result["hits"]["hits"]
    ledger_entry = ledger_hits[0]["_source"] if ledger_hits else None

    return {
        "status": doc.get("status"),
        "adjudication_id": doc.get("adjudication_id"),
        "cited_evidence": doc.get("cited_evidence", []),
        "generated_letter": doc.get("generated_letter"),
        "ledger_entry": ledger_entry,
        "decided_at": doc.get("decided_at"),
        "matched_policy": doc.get("matched_policy"),
        "trajectory_result": doc.get("trajectory_result"),
        "evidence_result": doc.get("evidence_result"),
        # Present on human reviewer decisions (decision_type=HUMAN_REVIEW);
        # the hospital claim view falls back to these for older claims.
        "decision_type": doc.get("decision_type"),
        "reviewer_comment": doc.get("reviewer_comment"),
        "decided_by": doc.get("decided_by"),
    }


@router.post("/{claim_id}/decision")
def submit_reviewer_decision(claim_id: str, body: ReviewerDecision):
    """
    ADDED (18 Sept): the insurance-reviewer detail page ("Approve" /
    "Deny" / "Request Info") previously only wrote the decision into
    browser localStorage (DemoDataManager) -- it never reached the
    backend at all, so a reviewer's call vanished on refresh and never
    touched insurance-claims or the audit ledger. This persists it for
    real:

    1. insurance-claims.status is updated via update_by_query, same
       pattern orchestrator.py already uses for the agent's own
       decisions, so the claim list / dashboard reflect it immediately.
    2. A new adjudication-results document records the human decision
       (decision_type=HUMAN_REVIEW), separate from any prior AI-agent
       result, and references that AI result's adjudication_id/status
       so the audit trail shows both what the agent recommended and what
       the reviewer actually decided.
    3. append_event() chains a REVIEWER_DECISION entry onto the same
       per-claim audit-ledger hash chain the agent's decisions use --
       verify_chain() covers human overrides exactly like AI ones.
    """
    es = get_es_client()
    hit = _find_claim(es, claim_id)
    status = _DECISION_TO_STATUS[body.decision]

    ai_result = es.search(
        index="adjudication-results",
        query={"term": {"claim_id": claim_id}},
        sort=[{"decided_at": "desc"}],
        size=1,
    )
    ai_hits = ai_result["hits"]["hits"]
    ai_adjudication_id = ai_hits[0]["_source"].get("adjudication_id") if ai_hits else None
    ai_status = ai_hits[0]["_source"].get("status") if ai_hits else None

    adjudication_id = f"REVIEW-{uuid.uuid4().hex[:10]}"
    decided_at = datetime.now(timezone.utc).isoformat()
    decision_doc = {
        "adjudication_id": adjudication_id,
        "claim_id": claim_id,
        "status": status,
        "cited_evidence": [],
        "generated_letter": f"Human reviewer decision: {status}. {body.reviewer_comment}",
        "decided_at": decided_at,
        "decided_by": body.reviewer_name,
        "decision_type": "HUMAN_REVIEW",
        "reviewer_comment": body.reviewer_comment,
        "ai_recommendation_id": ai_adjudication_id,
        "ai_recommended_status": ai_status,
    }
    es.index(index="adjudication-results", document=decision_doc, refresh="wait_for")

    # The reviewer's decision also lives on the claim record itself, so the
    # hospital side (which reads GET /claims/{id}) sees the status, comment
    # and who decided -- latest_review for display, review_history for the
    # full back-and-forth (e.g. REQUEST_INFO, then a later APPROVE).
    review = {
        "decision": body.decision,
        "status": status,
        "comment": body.reviewer_comment,
        "reviewer_name": body.reviewer_name,
        "decided_at": decided_at,
        "adjudication_id": adjudication_id,
        "ai_recommended_status": ai_status,
    }
    es.update_by_query(
        index=hit["_index"],
        query={"term": {"claim_id": claim_id}},
        script={
            "source": (
                "ctx._source.status = params.status;"
                "ctx._source.latest_review = params.review;"
                "if (ctx._source.review_history == null) { ctx._source.review_history = []; }"
                "ctx._source.review_history.add(params.review);"
            ),
            "params": {"status": status, "review": review},
        },
        refresh=True,
    )

    ledger_entry = append_event(
        claim_id,
        "REVIEWER_DECISION",
        {
            "adjudication_id": adjudication_id,
            "status": status,
            "reviewer_name": body.reviewer_name,
            "reviewer_comment": body.reviewer_comment,
            "ai_recommended_status": ai_status,
        },
        ref_id=adjudication_id,
    )

    return {
        "status": status,
        "adjudication_id": adjudication_id,
        "decided_at": decided_at,
        "decided_by": body.reviewer_name,
        "reviewer_comment": body.reviewer_comment,
        "ai_recommendation_id": ai_adjudication_id,
        "ai_recommended_status": ai_status,
        "ledger_entry": ledger_entry,
    }


@router.post("", status_code=201)
def create_claim(claim: ClaimCreate):
    es = get_es_client()

    claim_id = claim.claim_id or f"CLM-{uuid.uuid4().hex[:8].upper()}"

    existing = es.search(
        index=ALL_CLAIMS,
        query={"term": {"claim_id": claim_id}},
        size=1,
        ignore_unavailable=True,
    )
    if existing["hits"]["hits"]:
        raise HTTPException(status_code=409, detail=f"Claim {claim_id} already exists")

    doc = {
        "claim_id": claim_id,
        "patient_id": claim.patient_id,
        "payer_name": claim.payer_name,
        "cpt_code": claim.cpt_code,
        "icd10_code": claim.icd10_code,
        "claim_amount": claim.claim_amount,
        "claim_type": claim.claim_type,
        "submitted_date": datetime.now(timezone.utc).isoformat(),
        "status": "PENDING",
        "source": "manual",
        "attached_documents": [],
    }
    result = es.index(index=INSURANCE_CLAIMS, document=doc)
    es.indices.refresh(index=INSURANCE_CLAIMS)

    return {"id": result["_id"], **doc}
