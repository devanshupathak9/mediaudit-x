"""
OCR endpoints -- thin HTTP layer over app.pipeline.ocr. See INGESTION.md
section 6 for the contract this implements.

  POST /claims/{claim_id}/ocr                              run OCR on the claim's PENDING documents
  GET  /claims/{claim_id}/documents/{doc_id}/pages/{n}      one page's extracted text (for the review UI)
"""
from fastapi import APIRouter, Depends, HTTPException

from app.es_client import get_es_client
from app.indices.names import DOCUMENT_PAGES
from app.pipeline.ocr import get_ocr_service
from app.pipeline.ocr.service import OCRService

router = APIRouter(prefix="/claims", tags=["ocr"])


@router.post("/{claim_id}/ocr")
def run_claim_ocr(claim_id: str, service: OCRService = Depends(get_ocr_service)):
    results = service.process_claim(claim_id)
    return {"claim_id": claim_id, "documents": results}


@router.get("/{claim_id}/documents/{doc_id}/pages/{page_number}")
def get_document_page(claim_id: str, doc_id: str, page_number: int):
    es = get_es_client()
    result = es.search(
        index=DOCUMENT_PAGES,
        query={"bool": {"filter": [
            {"term": {"claim_id": claim_id}},
            {"term": {"doc_id": doc_id}},
            {"term": {"page_number": page_number}},
        ]}},
        size=1,
    )
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="Page not found")
    return hits[0]["_source"]
