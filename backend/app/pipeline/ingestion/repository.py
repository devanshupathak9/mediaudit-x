"""
Every Elasticsearch read/write the ingestion stage makes, in one place.

Claims created here go to claim-files; lookups by claim_id search both
claim-files and insurance-claims so documents can still be added to
manual/sample claims. The hit's _index says which one to write back to.

Writes use refresh="wait_for" because the very next step (the ledger
append, a duplicate check on the following upload, the UI reloading the
claim) searches for what was just written.
"""
from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS, CLAIM_DOCUMENTS, CLAIM_FILES
from app.tools.audit_ledger import append_event


class IngestionRepository:
    def __init__(self, es=None):
        self.es = es or get_es_client()

    def find_claim(self, claim_id: str) -> dict | None:
        """Raw hit ({"_index", "_id", "_source"}) from either claims index, or None."""
        result = self.es.search(
            index=ALL_CLAIMS,
            query={"term": {"claim_id": claim_id}},
            size=1,
            ignore_unavailable=True,
        )
        hits = result["hits"]["hits"]
        return hits[0] if hits else None

    def create_claim(self, claim: dict) -> str:
        result = self.es.index(index=CLAIM_FILES, document=claim, refresh="wait_for")
        return result["_id"]

    def update_claim(self, index: str, es_id: str, claim: dict) -> None:
        self.es.index(index=index, id=es_id, document=claim, refresh="wait_for")

    def delete_claim(self, es_id: str) -> None:
        self.es.delete(index=CLAIM_FILES, id=es_id, refresh="wait_for")

    def index_document(self, doc: dict) -> None:
        # doc_id doubles as the ES _id so rollback can delete by it.
        self.es.index(index=CLAIM_DOCUMENTS, id=doc["doc_id"], document=doc, refresh="wait_for")

    def delete_document(self, doc_id: str) -> None:
        self.es.delete(index=CLAIM_DOCUMENTS, id=doc_id, refresh="wait_for")

    def find_documents_by_sha256(self, hashes: list[str]) -> list[dict]:
        if not hashes:
            return []
        result = self.es.search(
            index=CLAIM_DOCUMENTS,
            query={"terms": {"sha256": hashes}},
            source=["doc_id", "claim_id", "sha256"],
            size=1000,
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def list_documents(self, claim_id: str) -> list[dict]:
        result = self.es.search(
            index=CLAIM_DOCUMENTS,
            query={"term": {"claim_id": claim_id}},
            sort=[{"uploaded_at": "asc"}],
            size=1000,
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def record_event(self, claim_id: str, event_type: str, payload: dict, ref_id: str | None = None) -> dict:
        return append_event(claim_id, event_type, payload, ref_id=ref_id)
