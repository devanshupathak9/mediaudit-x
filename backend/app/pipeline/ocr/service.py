"""
OCR stage: reads every PENDING document for a claim, extracts + chunks its
text, writes document-pages/document-chunks, and updates claim-documents'
ocr_status -- see INGESTION.md section 6 for the contract this implements.

Deterministic ids (page_id = "{doc_id}:p{n}", chunk_id =
"{doc_id}:p{n}:c{k}") plus deleting a document's previous pages/chunks
before re-writing (repository.clear_previous_output) make re-running OCR
on the same document safe.

A document that fails doesn't stop the batch: process_document catches
its own errors and reports FAILED for that one document, same "keep
going" rule the ingestion stage uses for a batch of files.
"""
import hashlib

from app.embeddings.embed import embed_text
from app.pipeline.ocr.chunker import chunk_page_text
from app.pipeline.ocr.extract import extract_document


class OCRService:
    def __init__(self, repository):
        self.repo = repository

    def process_claim(self, claim_id: str) -> list[dict]:
        return [self.process_document(doc) for doc in self.repo.find_pending_documents(claim_id)]

    def process_document(self, doc: dict) -> dict:
        doc_id, claim_id = doc["doc_id"], doc["claim_id"]
        try:
            data = self.repo.read_bytes(doc["source_uri"])
            pages = extract_document(data, doc["detected_type"])
        except Exception as exc:  # noqa: BLE001 -- one bad document must not stop the batch
            self.repo.update_document_status(doc_id, ocr_status="FAILED")
            self.repo.record_event(claim_id, "OCR_COMPLETED", {
                "doc_id": doc_id, "ocr_status": "FAILED", "error": str(exc),
            }, ref_id=doc_id)
            return {"doc_id": doc_id, "ocr_status": "FAILED", "error": str(exc)}

        page_docs, chunk_docs = self._build_pages_and_chunks(doc_id, claim_id, pages)

        self.repo.clear_previous_output(doc_id)
        self.repo.index_pages(page_docs)
        self.repo.index_chunks(chunk_docs)

        page_count = len(pages)
        ocr_status = "FAILED" if all(p.engine == "failed" for p in pages) else "DONE"
        engines = {p.engine for p in pages}
        ocr_engine = engines.pop() if len(engines) == 1 else "mixed"

        self.repo.update_document_status(
            doc_id, ocr_status=ocr_status, page_count=page_count, ocr_engine=ocr_engine,
        )

        text_sha256 = hashlib.sha256("\n".join(p.text for p in pages).encode("utf-8")).hexdigest()
        self.repo.record_event(claim_id, "OCR_COMPLETED", {
            "doc_id": doc_id, "page_count": page_count, "engine": ocr_engine,
            "ocr_status": ocr_status, "text_sha256": text_sha256,
        }, ref_id=doc_id)

        return {"doc_id": doc_id, "ocr_status": ocr_status, "page_count": page_count, "ocr_engine": ocr_engine}

    @staticmethod
    def _build_pages_and_chunks(doc_id: str, claim_id: str, pages) -> tuple[list[dict], list[dict]]:
        page_docs, chunk_docs = [], []
        for page in pages:
            page_docs.append({
                "page_id": f"{doc_id}:p{page.page_number}",
                "doc_id": doc_id,
                "claim_id": claim_id,
                "page_number": page.page_number,
                "text": page.text,
                "engine": page.engine,
                "ocr_confidence": page.ocr_confidence,
                "char_count": page.char_count,
            })
            for chunk in chunk_page_text(page.text, page.page_number, doc_id, claim_id):
                chunk_doc = {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "claim_id": chunk.claim_id,
                    "page_number": chunk.page_number,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "text": chunk.text,
                    "section": chunk.section,
                }
                vector = embed_text(chunk.text)
                if any(vector):  # Elasticsearch 9 rejects an all-zero vector for dot_product
                    chunk_doc["text_vector"] = vector
                chunk_docs.append(chunk_doc)
        return page_docs, chunk_docs
