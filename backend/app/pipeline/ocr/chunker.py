"""
Splits a single page's normalized text into paragraph-ish, offset-addressable
chunks for search (the document-chunks index) -- never crossing a page
boundary, since offsets only mean anything within the page they came from.

The one invariant every caller relies on, and that this module guarantees
by construction (see the slicing arithmetic in chunk_page_text, not a
post-hoc string search):

    page_text[chunk.char_start:chunk.char_end] == chunk.text
"""
import re
from dataclasses import dataclass

TARGET_CHUNK_CHARS = 650
MIN_CHUNK_CHARS = 500
MAX_CHUNK_CHARS = 800

_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
_SECTION_HEADER_RE = re.compile(
    r"^(assessment|plan|medications?|procedure|"
    r"history of present illness|hpi|impression|diagnosis|allergies)\s*:?\s*$",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    claim_id: str
    page_number: int
    char_start: int
    char_end: int
    text: str
    section: str | None


def _detect_section(text: str) -> str | None:
    """A section heading like 'Assessment:' on the chunk's first line."""
    first_line = text.split("\n", 1)[0].strip()
    match = _SECTION_HEADER_RE.match(first_line)
    return match.group(1).title() if match else None


def _split_points(text: str) -> list[int]:
    """Candidate break offsets: blank lines first, sentence ends as filler."""
    points = {m.start() for m in _BLANK_LINE_RE.finditer(text)}
    points |= {m.start() for m in _SENTENCE_END_RE.finditer(text)}
    return sorted(points)


def chunk_page_text(text: str, page_number: int, doc_id: str, claim_id: str) -> list[Chunk]:
    if not text:
        return []

    breakpoints = _split_points(text)
    chunks: list[Chunk] = []
    start = 0
    n = len(text)

    while start < n:
        target_end = min(start + TARGET_CHUNK_CHARS, n)
        if target_end == n:
            end = n
        else:
            candidates = [
                p for p in breakpoints
                if start + MIN_CHUNK_CHARS <= p <= start + MAX_CHUNK_CHARS
            ]
            end = max(candidates) if candidates else target_end
        end = max(end, start + 1)  # guarantee forward progress

        raw = text[start:end]
        lstripped = raw.lstrip()
        lead = len(raw) - len(lstripped)
        stripped = lstripped.rstrip()

        if stripped:
            local_start = start + lead
            local_end = local_start + len(stripped)
            index = len(chunks)
            chunks.append(Chunk(
                chunk_id=f"{doc_id}:p{page_number}:c{index}",
                doc_id=doc_id,
                claim_id=claim_id,
                page_number=page_number,
                char_start=local_start,
                char_end=local_end,
                text=stripped,
                section=_detect_section(stripped),
            ))

        start = end

    return chunks
