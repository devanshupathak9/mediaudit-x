"""
Audit trail endpoints for browsing the hash-chained ledger.

Exposes the tamper-evident audit-ledger entries so the UI can display
a complete history of all claim events (creation, adjudication,
reviewer decisions, document uploads) with chain verification.
"""
from fastapi import APIRouter, HTTPException
from app.es_client import get_es_client
from app.tools.audit_ledger import verify_chain, LEDGER_INDEX

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/entries")
def list_all_audit_entries(limit: int = 100, offset: int = 0):
    """
    Returns all audit ledger entries across all claims, most recent first.
    Use for the global audit trail browser.
    """
    es = get_es_client()

    result = es.search(
        index=LEDGER_INDEX,
        query={"match_all": {}},
        sort=[{"timestamp": "desc"}],
        from_=offset,
        size=limit,
    )

    hits = result["hits"]["hits"]
    entries = [
        {
            **hit["_source"],
            "_id": hit["_id"],
            "_score": hit.get("_score"),
        }
        for hit in hits
    ]

    return {
        "entries": entries,
        "total": result["hits"]["total"]["value"],
        "offset": offset,
        "limit": limit,
    }


@router.get("/entries/{claim_id}")
def list_claim_audit_entries(claim_id: str):
    """
    Returns all audit ledger entries for a specific claim, in chronological order.
    """
    es = get_es_client()

    result = es.search(
        index=LEDGER_INDEX,
        query={"term": {"claim_id": claim_id}},
        sort=[{"sequence_number": "asc"}],
        size=1000,
    )

    hits = result["hits"]["hits"]
    entries = [
        {
            **hit["_source"],
            "_id": hit["_id"],
        }
        for hit in hits
    ]

    return {
        "claim_id": claim_id,
        "entries": entries,
        "total": len(entries),
    }


@router.get("/verify/{claim_id}")
def verify_claim_chain(claim_id: str):
    """
    Verifies the hash chain for a specific claim.
    Returns whether the chain is intact (no tampering detected).
    """
    try:
        is_valid = verify_chain(claim_id)
        return {
            "claim_id": claim_id,
            "chain_valid": is_valid,
            "message": "Chain is intact" if is_valid else "Chain has been tampered with",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/stats")
def get_audit_stats():
    """
    Returns statistics about the audit ledger (total entries, claims with entries, etc).
    """
    es = get_es_client()

    # Total entries
    total_result = es.count(index=LEDGER_INDEX, query={"match_all": {}})
    total_entries = total_result["count"]

    # Unique claims - try both with and without .keyword suffix
    try:
        agg_result = es.search(
            index=LEDGER_INDEX,
            query={"match_all": {}},
            size=0,
            aggs={
                "unique_claims": {
                    "cardinality": {
                        "field": "claim_id"
                    }
                },
                "event_types": {
                    "terms": {
                        "field": "event_type",
                        "size": 20,
                        "missing": "ADJUDICATION"
                    }
                }
            }
        )

        unique_claims = agg_result["aggregations"]["unique_claims"]["value"]
        event_type_buckets = agg_result["aggregations"]["event_types"]["buckets"]

        event_type_counts = {
            bucket["key"]: bucket["doc_count"]
            for bucket in event_type_buckets
        }
    except Exception as e:
        # Fallback if aggregations fail
        unique_claims = 0
        event_type_counts = {}

    return {
        "total_entries": total_entries,
        "unique_claims": unique_claims,
        "event_types": event_type_counts,
    }
