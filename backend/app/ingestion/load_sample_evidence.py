"""
Loads data/sample/sample_referral_letter.pdf into `document-pages` as real
OCR'd text (via pdfplumber, one row per page) against claim CLM-1001
(patient PAT-883910, already in sample_claims.json: UnitedHealthcare,
cpt_code=27447, icd10_code=M17.11) -- a stand-in for the real OCR stage
(see INGESTION.md section 6, not merged yet) so
claim_draft_tool.fetch_claim_ocr_documents() can be tested against real
document-pages data today.

Field names match the document-pages contract INGESTION.md specifies
exactly (page_id, doc_id, claim_id, page_number, text, engine,
ocr_confidence, char_count) -- when OCR actually lands, real writes there
should look the same, no changes needed on the reading side.

Run with: python -m app.ingestion.load_sample_evidence
"""
import logging
from pathlib import Path

import pdfplumber

from app.es_client import get_es_client
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

DOCUMENT_PAGES_INDEX = "document-pages"
PDF_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sample" / "sample_referral_letter.pdf"
CLAIM_ID = "CLM-1001"
DOC_ID = "DOC-SAMPLE-REFERRAL"


def load():
    es = get_es_client()
    with pdfplumber.open(PDF_PATH) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]

    for page_number, text in enumerate(pages, start=1):
        if not text.strip():
            logger.warning("Page %d of %s extracted no text -- skipping", page_number, PDF_PATH.name)
            continue
        page_id = f"{DOC_ID}:p{page_number}"
        doc = {
            "page_id": page_id,
            "doc_id": DOC_ID,
            "claim_id": CLAIM_ID,
            "page_number": page_number,
            "text": text,
            "engine": "pdfplumber",
            "ocr_confidence": 1.0,  # text layer, not OCR'd from an image
            "char_count": len(text),
        }
        es.index(index=DOCUMENT_PAGES_INDEX, id=page_id, document=doc)
        logger.info("Indexed page %d (%d chars) for claim=%s doc=%s", page_number, len(text), CLAIM_ID, DOC_ID)

    es.indices.refresh(index=DOCUMENT_PAGES_INDEX)
    logger.info("Loaded %d page(s) from %s -> %s (claim_id=%s, doc_id=%s)",
                len(pages), PDF_PATH.name, DOCUMENT_PAGES_INDEX, CLAIM_ID, DOC_ID)


if __name__ == "__main__":
    configure_logging()
    load()
