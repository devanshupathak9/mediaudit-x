"""
CMS LCD/NCD policy PDF -> medical-policies ingestion.

BUILT LIVE (16 Sept), partially blocked: cms.gov's own bot-protection
(Akamai) returned "Access Denied" on every path tried from this
environment's browser session, including the plain domain root -- not a
permission problem (this session already has this site approved), CMS's
firewall is rejecting the request before it renders. That's a server-side
block this tool doesn't try to route around.

So this script can't fetch the PDF itself yet. What it DOES do, and does
for real: given a real LCD/NCD PDF you've downloaded yourself (from
cms.gov/medicare-coverage-database in a normal browser -- search e.g.
"total knee arthroplasty" to find an LCD with real step-therapy language),
extracts real text with pdfplumber and applies heuristics to structure it
into the medical-policies schema:
  - title: first non-empty line of extracted text
  - cpt_codes / icd10_codes: regex-matched from the actual document text
  - clinical_indications: text between a "Coverage Indications" (or
    similar) heading and the next section heading
  - contraindications: text after a "Limitations" heading
  - step_therapy_required: True if the indications text mentions
    conservative/physical therapy alongside a duration ("months"/"weeks")

IMPORTANT: this is heuristic text extraction from a legally significant
document, not a verified parse. Read the extracted fields against the
source PDF before trusting them in a demo or a judge Q&A -- do not treat
the auto-extracted step_therapy_required / clinical_indications as
verified without a human checking them against the actual policy text.

Usage:
    python -m app.ingestion.ingest_policies /path/to/downloaded_lcd.pdf \\
        --payer "UnitedHealthcare" --policy-id "POL-UHC-KNEE-02"
"""
import argparse
import re
from pathlib import Path

import pdfplumber

from app.es_client import get_es_client
from app.embeddings.embed import embed_text

CPT_RE = re.compile(r"\b\d{5}\b")
ICD10_RE = re.compile(r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b")

INDICATIONS_HEADINGS = [
    "Coverage Indications, Limitations, and/or Medical Necessity",
    "Indications and Limitations of Coverage",
    "Coverage Guidance",
    "Coverage Indications",
]
LIMITATIONS_HEADINGS = ["Limitations", "Contraindications", "Exclusions"]


def extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _find_heading_end(text: str, headings: list[str], search_from: int = 0) -> int | None:
    """
    Finds the earliest occurrence of any heading at or after search_from,
    skipping a match if it's immediately followed by more heading-like
    text on the same line (a crude guard against one heading's text
    containing another heading as a substring, e.g. "Coverage
    Indications, Limitations, and/or Medical Necessity" containing the
    word "Limitations"). Returns the index right after the matched
    heading, or None if nothing matched.
    """
    best = None
    for h in headings:
        idx = text.find(h, search_from)
        if idx == -1:
            continue
        line_end = text.find("\n", idx)
        line_end = line_end if line_end != -1 else len(text)
        # if this heading is immediately followed by more comma-joined
        # heading text on the same line, it's embedded in a bigger
        # heading, not a real section break -- skip it.
        remainder_on_line = text[idx + len(h):line_end].lstrip()
        if remainder_on_line.startswith((",", "and", "&")):
            continue
        end = idx + len(h)
        if best is None or end < best:
            best = end
    return best


def _section_between(text: str, start_headings: list[str], end_headings: list[str], search_from: int = 0) -> tuple[str, int]:
    start_idx = _find_heading_end(text, start_headings, search_from)
    if start_idx is None:
        return "", search_from
    end_idx = _find_heading_end(text, end_headings, start_idx)
    if end_idx is None:
        end_idx = len(text)
    else:
        # end_idx from _find_heading_end is past the heading text; we want
        # the section content to stop at the START of that heading instead.
        for h in end_headings:
            idx = text.find(h, start_idx)
            if idx != -1 and idx < end_idx:
                end_idx = idx
    return text[start_idx:end_idx].strip(), end_idx


def parse_policy_pdf(pdf_path: Path) -> dict:
    text = extract_text(pdf_path)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0] if lines else pdf_path.stem

    clinical_indications, indications_end = _section_between(text, INDICATIONS_HEADINGS, LIMITATIONS_HEADINGS)
    contraindications, _ = _section_between(text, LIMITATIONS_HEADINGS, ["Coding Information", "Bibliography"], search_from=indications_end)

    cpt_codes = sorted(set(CPT_RE.findall(clinical_indications or text)))
    icd10_codes = sorted(set(ICD10_RE.findall(clinical_indications or text)))

    step_therapy_required = bool(
        re.search(r"(conservative|physical) therap", clinical_indications, re.IGNORECASE)
        and re.search(r"\b(month|week)s?\b", clinical_indications, re.IGNORECASE)
    )

    return {
        "title": title,
        "cpt_codes": " ".join(cpt_codes[:20]),
        "icd10_codes": " ".join(icd10_codes[:20]),
        "clinical_indications": clinical_indications[:4000] or "(heading not found -- check the source PDF's section names, this parser's INDICATIONS_HEADINGS list may need a new entry)",
        "contraindications": contraindications[:2000],
        "step_therapy_required": step_therapy_required,
        "_raw_text_length": len(text),
    }


def ingest(pdf_path: Path, payer_name: str, policy_id: str, dry_run: bool = False) -> dict:
    parsed = parse_policy_pdf(pdf_path)
    raw_len = parsed.pop("_raw_text_length")

    doc = {
        "policy_id": policy_id,
        "payer_name": payer_name,
        "title": parsed["title"],
        "cpt_codes": parsed["cpt_codes"],
        "icd10_codes": parsed["icd10_codes"],
        "clinical_indications": parsed["clinical_indications"],
        "contraindications": parsed["contraindications"],
        "step_therapy_required": parsed["step_therapy_required"],
    }
    doc["policy_vector"] = embed_text(f"{doc['title']} {doc['clinical_indications']}")

    print(f"Extracted {raw_len} characters from {pdf_path.name}")
    print(f"Title: {doc['title']}")
    print(f"CPT codes found: {doc['cpt_codes']}")
    print(f"ICD-10 codes found: {doc['icd10_codes']}")
    print(f"step_therapy_required: {doc['step_therapy_required']}")
    print("--- clinical_indications (first 500 chars) ---")
    print(doc["clinical_indications"][:500])
    print("--- REVIEW THIS AGAINST THE SOURCE PDF BEFORE TRUSTING IT ---")

    if not dry_run:
        es = get_es_client()
        # FIXED (18 Sept): stable id=policy_id, same idempotency fix as
        # the other loaders.
        es.index(index="medical-policies", document=doc, id=policy_id)
        es.indices.refresh(index="medical-policies")
        print(f"[loaded] -> medical-policies as {policy_id}")
    else:
        print("[dry run] not written to Elasticsearch")

    return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--payer", required=True)
    parser.add_argument("--policy-id", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Parse and print only, don't write to Elasticsearch")
    args = parser.parse_args()

    ingest(args.pdf_path, args.payer, args.policy_id, dry_run=args.dry_run)
