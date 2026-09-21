"""
Rejection -> ranker feedback loop.

When a coder rejects a drafted code and supplies the correct one, that
becomes a learned correction: future runs score the corrected code higher
(and the rejected one lower) for text that resembles what the coder was
looking at (see ranker._learned_adjustment). This is what lets the local
dictionary + ranker improve from coder review instead of staying static.
"""
import json
import logging
from datetime import datetime, timezone

from app.drafting.dictionary import LEARNED_CORRECTIONS_PATH, load_learned_corrections

logger = logging.getLogger(__name__)


def record_rejection(claim_id: str, field_type: str, rejected_code: str,
                      corrected_code: str, cited_text: str) -> None:
    """field_type is e.g. "CPT" or "ICD10CM" -- whatever code_system the
    rejected/corrected codes belong to."""
    if not rejected_code or not corrected_code or rejected_code == corrected_code:
        return
    corrections = load_learned_corrections()
    corrections.append({
        "claim_id": claim_id,
        "field_type": field_type,
        "rejected_code": rejected_code,
        "corrected_code": corrected_code,
        "cited_text": cited_text,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    LEARNED_CORRECTIONS_PATH.write_text(json.dumps(corrections, indent=2), encoding="utf-8")
    logger.info("Recorded correction for claim %s: %s -> %s (field=%s)",
                claim_id, rejected_code, corrected_code, field_type)
