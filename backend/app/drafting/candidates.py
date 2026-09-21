"""
Deterministic candidate generation -- regex + local code-dictionary phrase
matching, per ARCHITECTURE.md Stage 3a's exact patterns. Runs over OCR page
text (document-pages), no LLM, no embeddings.

This is the safety net the LLM's own knowledge/web-search pass doesn't
have on its own: OCR.md's real testing found Tesseract silently misreads
digits on some fonts (e.g. "0" -> "@"), which could corrupt a code in the
raw text. A regex hit is kept ONLY if it exists in the local dictionary --
that membership check is what actually filters out corrupted/false-positive
matches (dates, MRNs, garbled digits), not the regex alone.
"""
import logging
import re

logger = logging.getLogger(__name__)

CPT_CODE_RE = re.compile(r"\b\d{4}[0-9FTU]\b")
ICD10_CODE_RE = re.compile(r"\b[A-TV-Z]\d[0-9A-Z](?:\.[0-9A-Z]{1,4})?\b")

NEGATION_TERMS = ("no ", "denies", "denied", "rule out", "r/o", "ruled out")
HISTORICAL_TERMS = ("history of", "h/o")
CONTEXT_WINDOW = 40  # chars scanned before a match for a negation/historical cue


def _preceding_context(text: str, start: int) -> str:
    return text[max(0, start - CONTEXT_WINDOW):start].lower()


def _tag_context(preceding: str) -> str | None:
    if any(t in preceding for t in NEGATION_TERMS):
        return "negated"
    if any(t in preceding for t in HISTORICAL_TERMS):
        return "historical"
    return None


def regex_candidates(doc, code_dictionary: list[dict]) -> list[dict]:
    """Pulls code-shaped tokens from each page and keeps only ones that
    exist in the local dictionary."""
    by_code = {e["code"].upper(): e for e in code_dictionary}
    candidates = []
    for block in doc.blocks:
        for pattern in (CPT_CODE_RE, ICD10_CODE_RE):
            for m in pattern.finditer(block.text):
                entry = by_code.get(m.group(0).upper())
                if not entry:
                    continue
                candidates.append({
                    "code_system": entry["code_system"],
                    "code": entry["code"],
                    "display": entry["display"],
                    "doc_id": block.doc_id,
                    "page_number": block.page_number,
                    "char_start": m.start(),
                    "char_end": m.end(),
                    "text": block.text[m.start():m.end()],
                    "method": "regex",
                    "score": 1.0,
                    "context": _tag_context(_preceding_context(block.text, m.start())),
                })
    return candidates


def dictionary_phrase_candidates(doc, code_dictionary: list[dict]) -> list[dict]:
    """Case-insensitive substring match of each dictionary entry's display
    text or a synonym against the page text."""
    candidates = []
    for block in doc.blocks:
        lower_text = block.text.lower()
        for entry in code_dictionary:
            for phrase in [entry["display"], *entry.get("synonyms", [])]:
                idx = lower_text.find(phrase.lower())
                if idx == -1:
                    continue
                candidates.append({
                    "code_system": entry["code_system"],
                    "code": entry["code"],
                    "display": entry["display"],
                    "doc_id": block.doc_id,
                    "page_number": block.page_number,
                    "char_start": idx,
                    "char_end": idx + len(phrase),
                    "text": block.text[idx: idx + len(phrase)],
                    "method": "dictionary",
                    "score": 0.7,
                    "context": _tag_context(_preceding_context(block.text, idx)),
                })
                break  # one match per entry per block is enough signal
    return candidates


def gather_local_candidates(doc, code_dictionary: list[dict]) -> list[dict]:
    """Regex + dictionary-phrase passes, merged. Doesn't de-dupe across
    method -- a code found both ways is stronger evidence, and the ranker
    wants every supporting span, not just one."""
    candidates = regex_candidates(doc, code_dictionary) + dictionary_phrase_candidates(doc, code_dictionary)
    logger.info(
        "Local candidate generation: %d hit(s) (%d regex, %d dictionary)",
        len(candidates),
        sum(1 for c in candidates if c["method"] == "regex"),
        sum(1 for c in candidates if c["method"] == "dictionary"),
    )
    return candidates
