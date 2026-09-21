"""
Small, local, licensing-safe code dictionary.

CPT descriptors are AMA-licensed, so this ships only a curated subset
covering the demo/sample/synthea data with our own short descriptions
(see data/codes/code_dictionary.json) -- not the full CMS/AMA code sets.
ARCHITECTURE.md's own Stage 3a spec says as much: "CPT: AMA-licensed --
ship only a small curated subset... say so in the README."

data/codes/learned_corrections.json starts empty and grows via
feedback.record_rejection() whenever a coder rejects a drafted code and
supplies the correct one -- this is the ranker's feedback loop, not a
static reference set. Read fresh every call (not cached) since it's
written to at runtime and the next draft should see the latest corrections
immediately.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "codes"
CODE_DICTIONARY_PATH = DATA_DIR / "code_dictionary.json"
LEARNED_CORRECTIONS_PATH = DATA_DIR / "learned_corrections.json"


def load_code_dictionary() -> list[dict]:
    return json.loads(CODE_DICTIONARY_PATH.read_text(encoding="utf-8"))


def load_learned_corrections() -> list[dict]:
    if not LEARNED_CORRECTIONS_PATH.exists():
        return []
    return json.loads(LEARNED_CORRECTIONS_PATH.read_text(encoding="utf-8"))


def code_lookup(code_dictionary: list[dict], code: str) -> dict | None:
    code = code.strip().upper()
    for entry in code_dictionary:
        if entry["code"].upper() == code:
            return entry
    return None
