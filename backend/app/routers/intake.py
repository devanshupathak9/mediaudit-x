"""
Document ingestion endpoints — thin HTTP layer over
app.pipeline.ingestion (all validation and storage logic lives there).

  POST /claims/intake                 new claim (DRAFT) from uploaded documents
  POST /claims/{claim_id}/documents   add documents to an open claim
  GET  /claims/{claim_id}/documents   registered documents for a claim

Error bodies keep `detail` a plain string (the frontend shows it as-is)
and add a machine-readable `code` plus per-file `rejected` reasons.

When a DRAFT claim receives documents, automatic processing (OCR -> draft
-> PENDING, app/pipeline/processing.py) is started as a background task
after the response is sent, so the upload itself stays fast.
"""
import json
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.pipeline.ingestion import get_ingestion_service
from app.pipeline.ingestion.models import ClaimIntake, IncomingFile, IngestionError
from app.pipeline.ingestion.service import IngestionService
from app.pipeline.processing import process_claim_in_background

router = APIRouter(prefix="/claims", tags=["ingestion"])


async def _read_uploads(uploads: list[UploadFile], service: IngestionService) -> list[IncomingFile]:
    limit = service.limits.max_file_bytes
    files = []
    for upload in uploads:
        # Read one byte past the limit: enough to know it's too big
        # without pulling an arbitrarily large body into memory.
        data = await upload.read(limit + 1)
        files.append(IncomingFile(
            filename=upload.filename or "",
            data=data[:limit],
            client_mime_type=upload.content_type,
            truncated=len(data) > limit,
        ))
    return files


def _error(e: IngestionError) -> JSONResponse:
    return JSONResponse(status_code=e.http_status, content={
        "detail": e.message,
        "code": e.code,
        "rejected": [asdict(r) for r in e.rejected],
    })


def _schedule_processing(background_tasks: BackgroundTasks, claim: dict, accepted: list) -> None:
    if accepted and claim.get("status") == "DRAFT":
        background_tasks.add_task(process_claim_in_background, claim["claim_id"])


@router.post("/intake", status_code=201)
async def intake_claim(
    background_tasks: BackgroundTasks,
    patient_id: str | None = Form(None),
    payer_name: str | None = Form(None),
    claim_type: str = Form("professional"),
    submitted_by: str = Form("unknown"),
    claim_amount: float | None = Form(None),
    # Optional JSON object with the hospital form's details (patient,
    # clinical, admission, services, hospital, insurance,
    # estimated_total_cost); see ClaimDetails in pipeline/ingestion/models.py.
    details: str | None = Form(None),
    claim_id: str | None = Form(None),
    doc_type: str = Form("supporting_document"),
    files: list[UploadFile] | None = File(None),
    service: IngestionService = Depends(get_ingestion_service),
):
    try:
        meta = ClaimIntake(
            patient_id=patient_id,
            payer_name=payer_name,
            claim_type=claim_type,
            submitted_by=submitted_by,
            claim_amount=claim_amount,
            details=json.loads(details) if details else None,
            claim_id=claim_id,
        )
    except json.JSONDecodeError:
        return JSONResponse(status_code=422, content={
            "detail": "details must be a JSON object", "code": "invalid_claim_fields", "rejected": [],
        })
    except ValidationError as e:
        first = e.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        return JSONResponse(status_code=422, content={
            "detail": f"{field}: {first['msg']}", "code": "invalid_claim_fields", "rejected": [],
        })

    try:
        result = service.intake(meta, await _read_uploads(files or [], service), doc_type)
    except IngestionError as e:
        return _error(e)

    _schedule_processing(background_tasks, result.claim, result.accepted)
    return {
        "claim": result.claim,
        "accepted": result.accepted,
        "rejected": [asdict(r) for r in result.rejected],
    }


@router.post("/{claim_id}/documents", status_code=201)
async def upload_claim_documents(
    claim_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),  # single-file field the existing frontend sends
    doc_type: str = Form("supporting_document"),
    uploaded_by: str = Form("unknown"),
    service: IngestionService = Depends(get_ingestion_service),
):
    uploads = [*(files or []), *([file] if file else [])]
    try:
        result = service.add_documents(claim_id, await _read_uploads(uploads, service), doc_type, uploaded_by)
    except IngestionError as e:
        return _error(e)

    _schedule_processing(background_tasks, result.claim, result.accepted)
    first = result.accepted[0]
    return {
        # Pre-pipeline response fields, kept for existing callers.
        "doc_id": first["doc_id"],
        "source_uri": first["source_uri"],
        "claim": result.claim,
        "accepted": result.accepted,
        "rejected": [asdict(r) for r in result.rejected],
    }


@router.get("/{claim_id}/documents")
def list_claim_documents(
    claim_id: str,
    service: IngestionService = Depends(get_ingestion_service),
):
    try:
        return service.list_documents(claim_id)
    except IngestionError as e:
        return _error(e)
