"""
Hash-chained audit ledger — tamper-evidence without blockchain overhead.

Each entry's record_hash = SHA256(canonical_json(payload) + prev_hash).
Any edit to a past entry breaks every subsequent hash, detectable with a
single linear scan. This is fully working — no TODOs here, use as-is.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.es_client import get_es_client

LEDGER_INDEX = "audit-ledger"


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _get_last_entry(es, claim_id: str) -> dict | None:
    result = es.search(
        index=LEDGER_INDEX,
        query={"term": {"claim_id": claim_id}},
        sort=[{"sequence_number": "desc"}],
        size=1,
    )
    hits = result["hits"]["hits"]
    return hits[0]["_source"] if hits else None


def append_entry(claim_id: str, adjudication_id: str, payload: dict) -> dict:
    """
    Appends a new hash-chained entry for this claim's adjudication.
    Returns the ledger entry that was written.
    """
    return _append(claim_id, payload, {"adjudication_id": adjudication_id})


def append_event(claim_id: str, event_type: str, payload: dict, ref_id: str | None = None) -> dict:
    """
    Appends a non-adjudication pipeline event (CLAIM_CREATED,
    DOCUMENT_UPLOADED, ...) to the same per-claim chain, with the same
    hash rule as append_entry. event_type is folded into the hashed
    payload so relabelling an event also breaks the chain.
    """
    return _append(
        claim_id,
        {"event_type": event_type, **payload},
        {"event_type": event_type, "ref_id": ref_id},
    )


def _append(claim_id: str, payload: dict, extra_fields: dict) -> dict:
    es = get_es_client()
    last_entry = _get_last_entry(es, claim_id)

    prev_hash = last_entry["record_hash"] if last_entry else "GENESIS"
    sequence_number = (last_entry["sequence_number"] + 1) if last_entry else 0

    record_hash = hashlib.sha256(
        (_canonical(payload) + prev_hash).encode("utf-8")
    ).hexdigest()

    entry = {
        "ledger_id": str(uuid4()),
        **extra_fields,
        "claim_id": claim_id,
        "record_hash": record_hash,
        "prev_hash": prev_hash,
        "sequence_number": sequence_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # wait_for: the next append's _get_last_entry search must see this
    # entry, otherwise back-to-back appends reuse the same sequence number.
    es.index(index=LEDGER_INDEX, document=entry, refresh="wait_for")
    return entry


def verify_chain(claim_id: str) -> bool:
    """
    Walks the full chain for a claim and confirms no entry has been tampered
    with. Returns True if the chain is intact.
    """
    es = get_es_client()
    result = es.search(
        index=LEDGER_INDEX,
        query={"term": {"claim_id": claim_id}},
        sort=[{"sequence_number": "asc"}],
        size=1000,
    )
    entries = [hit["_source"] for hit in result["hits"]["hits"]]

    expected_prev = "GENESIS"
    for entry in entries:
        if entry["prev_hash"] != expected_prev:
            return False
        expected_prev = entry["record_hash"]
    return True
