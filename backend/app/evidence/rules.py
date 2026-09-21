"""
Small, deterministic consistency rules for the evidence check (Stage 6) --
not payer policy, just the kind of sanity check a human coder would do at
a glance. Can only downgrade a result, never upgrade one.
"""
from app.drafting.dictionary import code_lookup

LATERALITY_TERMS = {"right": "left", "left": "right"}


def check_laterality(code: str, code_dictionary: list[dict], cited_text: str) -> bool:
    """
    Returns True (caller should downgrade the result to WEAK) if the
    code's own dictionary display names a side (right/left) that the
    cited text names the *opposite* of -- e.g. code says "right knee" but
    the supporting text only says "left knee". A cited_text that mentions
    neither side, or the same side, is not flagged.
    """
    entry = code_lookup(code_dictionary, code)
    if not entry:
        return False
    display_lower = entry["display"].lower()
    cited_lower = cited_text.lower()
    for side, opposite in LATERALITY_TERMS.items():
        if side in display_lower and opposite in cited_lower and side not in cited_lower:
            return True
    return False
