"""
One-time backfill: syncs insurance-claims.status from the latest
adjudication-results entry for each claim.

Why this exists: orchestrator.py only started writing the decided status
back to insurance-claims (via update_by_query) after the Bedrock-auth /
persistence fix landed. Any claim that was adjudicated *before* that fix
still has status=PENDING in insurance-claims even though a real decision
(APPROVED/DENIED/NEEDS_REVIEW) already exists in adjudication-results and
audit-ledger. This script finds those and repairs insurance-claims so the
home page and claim list reflect the true decision without needing to
re-run adjudication.

Safe to re-run.

Usage:
    cd backend && source venv/bin/activate && python3 scripts/backfill_claim_status.py
"""
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from app.es_client import get_es_client  # noqa: E402


def main():
    es = get_es_client()

    # Pull every adjudication-results doc, keep only the most recent per claim_id.
    latest_by_claim = {}
    resp = es.search(
        index="adjudication-results",
        query={"match_all": {}},
        sort=[{"decided_at": "desc"}],
        size=500,
    )
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        cid = src.get("claim_id")
        if cid and cid not in latest_by_claim:
            latest_by_claim[cid] = src.get("status")

    if not latest_by_claim:
        print("No adjudication-results found -- nothing to backfill.")
        return

    updated, already_correct, missing = [], [], []
    for claim_id, decided_status in latest_by_claim.items():
        claim_resp = es.search(
            index="insurance-claims",
            query={"term": {"claim_id": claim_id}},
            size=1,
        )
        hits = claim_resp["hits"]["hits"]
        if not hits:
            missing.append(claim_id)
            continue
        current_status = hits[0]["_source"].get("status")
        if current_status == decided_status:
            already_correct.append(claim_id)
            continue
        result = es.update_by_query(
            index="insurance-claims",
            query={"term": {"claim_id": claim_id}},
            script={
                "source": "ctx._source.status = params.status",
                "params": {"status": decided_status},
            },
            refresh=True,
        )
        updated.append((claim_id, current_status, decided_status, result.get("updated", 0)))

    print(f"Checked {len(latest_by_claim)} claim(s) with adjudication results.\n")
    if updated:
        print(f"Updated {len(updated)} claim(s):")
        for claim_id, old, new, n in updated:
            print(f"  {claim_id}: {old!r} -> {new!r} ({n} doc updated)")
    if already_correct:
        print(f"\nAlready correct: {len(already_correct)} claim(s) -- {sorted(already_correct)}")
    if missing:
        print(f"\nWARNING -- adjudication result exists but no matching insurance-claims doc: {sorted(missing)}")


if __name__ == "__main__":
    main()
