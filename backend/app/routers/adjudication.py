"""
Adjudication endpoint — wired to the real agent orchestrator.

BUILT LIVE (18 Sept): replaces the placeholder event stream with the real
multi-step loop in app.agent.orchestrator. Each yielded (event, data) pair
from the orchestrator becomes one SSE event; the frontend distinguishes
"reasoning_step" / "interaction_alert" / "done" event names exactly as
specified in the build spec's API reference.

Every stream ends in either "done" or "error" -- never silently.

A DRAFT claim is processed first, inside this same stream (OCR -> draft ->
PENDING, app/pipeline/processing.py), with its steps sent as
reasoning_step events. If a background upload task is already processing
it (status PROCESSING), the stream waits for that to finish.

Then _adjudication_blocker() refuses claims that still aren't ready:
  - any non-adjudicable status (e.g. processing failed and it's DRAFT);
  - a claim a human reviewer has already decided (latest_review set):
    re-running would overwrite the reviewer's status with the agent's;
  - a missing patient_id / payer_name / cpt_code / icd10_code: every tool
    filters on these, and Elasticsearch rejects a term query on null.
An AI-only decision (APPROVED/DENIED/REQUEST_INFO with no human review)
can still be re-run, which the seeded demo claims and scripts/e2e_check.py
rely on.
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS
from app.agent.orchestrator import adjudicate_claim
from app.pipeline.processing import ProcessingFailed, process_claim

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["adjudication"])

ADJUDICABLE_STATUSES = frozenset({"PENDING", "APPROVED", "DENIED", "REQUEST_INFO"})

PROCESSING_WAIT_SECONDS = 300
PROCESSING_POLL_SECONDS = 3

REQUIRED_FIELDS = {
    "patient_id": "patient ID",
    "payer_name": "payer / insurance company",
    "cpt_code": "CPT procedure code",
    "icd10_code": "ICD-10 diagnosis code",
}


def _load_claim(claim_id: str) -> dict:
    es = get_es_client()
    result = es.search(
        index=ALL_CLAIMS,
        query={"term": {"claim_id": claim_id}},
        size=1,
        ignore_unavailable=True,
    )
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="Claim not found")
    return hits[0]["_source"]


def _adjudication_blocker(claim: dict) -> dict | None:
    """Returns an error payload ({detail, code, ...}) if this claim can't be
    adjudicated yet, or None if it can."""
    status = claim.get("status")
    review = claim.get("latest_review")
    if review:
        return {
            "code": "already_reviewed",
            "detail": (
                f"Claim was already decided by a human reviewer "
                f"({review.get('reviewer_name', 'reviewer')}: {review.get('status', status)}). "
                "Re-running the AI analysis would overwrite that decision."
            ),
            "status": status,
        }
    if status not in ADJUDICABLE_STATUSES:
        return {
            "code": "claim_not_ready",
            "detail": (
                f"Claim is {status or 'missing a status'}; only a claim whose codes have been extracted from "
                "its documents (PENDING) can be adjudicated."
            ),
            "status": status,
        }
    missing = [label for field, label in REQUIRED_FIELDS.items() if not str(claim.get(field) or "").strip()]
    if missing:
        return {
            "code": "missing_fields",
            "detail": f"Claim can't be adjudicated without: {', '.join(missing)}.",
            "missing": missing,
            "status": status,
        }
    return None


def _step(step: str, detail: str) -> dict:
    return {"event": "reasoning_step", "data": json.dumps({"step": step, "detail": detail})}


async def _process_draft(claim_id: str):
    """Runs process_claim() in a worker thread (it makes blocking ES/LLM
    calls) and streams its steps as they happen. Raises ProcessingFailed."""
    loop = asyncio.get_running_loop()
    steps: asyncio.Queue = asyncio.Queue()

    def on_step(step: str, detail: str) -> None:
        loop.call_soon_threadsafe(steps.put_nowait, (step, detail))

    task = asyncio.ensure_future(asyncio.to_thread(process_claim, claim_id, on_step))
    while not (task.done() and steps.empty()):
        try:
            step, detail = await asyncio.wait_for(steps.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        yield _step(step, detail)
    task.result()


async def _wait_for_processing(claim_id: str):
    """Another worker (the upload's background task) is processing this
    claim; wait until its status moves on."""
    deadline = time.monotonic() + PROCESSING_WAIT_SECONDS
    yield _step("processing_wait", "Documents are still being processed (OCR + code extraction); waiting...")
    while time.monotonic() < deadline:
        await asyncio.sleep(PROCESSING_POLL_SECONDS)
        if (await asyncio.to_thread(_load_claim, claim_id)).get("status") != "PROCESSING":
            return
    raise ProcessingFailed(f"Document processing did not finish within {PROCESSING_WAIT_SECONDS}s; try again shortly.")


async def _event_stream(claim_id: str):
    try:
        claim = _load_claim(claim_id)
    except HTTPException as e:
        yield {"event": "error", "data": json.dumps({"detail": e.detail, "code": "claim_not_found"})}
        return

    try:
        if claim.get("status") == "PROCESSING":
            async for event in _wait_for_processing(claim_id):
                yield event
            claim = _load_claim(claim_id)
        if claim.get("status") == "DRAFT":
            async for event in _process_draft(claim_id):
                yield event
    except ProcessingFailed as e:
        yield {"event": "error", "data": json.dumps({"detail": str(e), "code": "processing_failed"})}
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("Processing failed for claim %s", claim_id)
        yield {"event": "error", "data": json.dumps({"detail": f"Processing failed: {e}", "code": "processing_failed"})}
        return
    claim = _load_claim(claim_id)

    blocker = _adjudication_blocker(claim)
    if blocker:
        yield {"event": "error", "data": json.dumps(blocker)}
        return

    try:
        async for event_name, data in adjudicate_claim(claim):
            yield {"event": event_name, "data": json.dumps(data, default=str)}
    except Exception as e:  # noqa: BLE001 - surface to the client instead of dropping the stream
        logger.exception("Adjudication failed for claim %s", claim_id)
        yield {"event": "error", "data": json.dumps({
            "detail": f"Adjudication failed: {e}", "code": "adjudication_failed",
        })}


@router.post("/{claim_id}/adjudicate")
async def adjudicate(claim_id: str):
    return EventSourceResponse(_event_stream(claim_id))
