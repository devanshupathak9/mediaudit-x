"""
Every Elasticsearch (and blob storage) read/write the OCR stage makes, in
one place -- same pattern as app/pipeline/ingestion/repository.py.
"""
from app.es_client import get_es_client
from app.indices.names import CLAIM_DOCUMENTS, DOCUMENT_CHUNKS, DOCUMENT_PAGES
from app.pipeline.ingestion.storage import LocalBlobStore
from app.tools.audit_ledger import append_event


class OCRRepository:
    def __init__(self, es=None, blob_store=None):
        self.es = es or get_es_client()
        self.blobs = blob_store or LocalBlobStore()

    def find_pending_documents(self, claim_id: str) -> list[dict]:
        result = self.es.search(
            index=CLAIM_DOCUMENTS,
            query={"bool": {"filter": [
                {"term": {"claim_id": claim_id}},
                {"term": {"ocr_status": "PENDING"}},
            ]}},
            size=1000,
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def read_bytes(self, source_uri: str) -> bytes:
        return self.blobs.read(source_uri)

    def clear_previous_output(self, doc_id: str) -> None:
        """Deletes this document's old pages/chunks before re-writing, so
        re-running OCR on a document is safe even if the new run produces
        fewer pages/chunks than the previous one (deterministic ids alone
        would leave stale extras behind)."""
        self.es.delete_by_query(
            index=DOCUMENT_PAGES, query={"term": {"doc_id": doc_id}}, conflicts="proceed",
        )
        self.es.delete_by_query(
            index=DOCUMENT_CHUNKS, query={"term": {"doc_id": doc_id}}, conflicts="proceed",
        )

    def index_pages(self, pages: list[dict]) -> None:
        for page in pages:
            self.es.index(index=DOCUMENT_PAGES, id=page["page_id"], document=page)
        if pages:
            self.es.indices.refresh(index=DOCUMENT_PAGES)

    def index_chunks(self, chunks: list[dict]) -> None:
        for chunk in chunks:
            self.es.index(index=DOCUMENT_CHUNKS, id=chunk["chunk_id"], document=chunk)
        if chunks:
            self.es.indices.refresh(index=DOCUMENT_CHUNKS)

    def update_document_status(self, doc_id: str, **fields) -> None:
        self.es.update(index=CLAIM_DOCUMENTS, id=doc_id, doc=fields, refresh="wait_for")

    def record_event(self, claim_id: str, event_type: str, payload: dict, ref_id: str | None = None) -> dict:
        return append_event(claim_id, event_type, payload, ref_id=ref_id)
