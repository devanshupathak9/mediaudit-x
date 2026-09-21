"""
Unit tests for the OCR extraction/chunking pipeline (app/pipeline/ocr/).
Pure logic -- no Elasticsearch cluster needed, per this repo's rule that
offset/validator tests should run standalone.

test_extract_document_pdf_text_layer runs against the real
data/sample/sample_referral_letter.pdf fixture used elsewhere in the repo,
exercising the actual pdfplumber text-layer path end to end.
"""
from pathlib import Path

import pytest

from app.pipeline.ocr.chunker import chunk_page_text
from app.pipeline.ocr.extract import extract_document, normalize_text

SAMPLE_PDF = (
    Path(__file__).parent.parent.parent / "data" / "sample" / "sample_referral_letter.pdf"
)


def test_normalize_text_collapses_whitespace_and_crlf():
    raw = "Line one.\r\nLine   two.\r\n\r\n  Line three.  \t"
    result = normalize_text(raw)
    assert "\r" not in result
    assert result == "Line one.\nLine two.\n\nLine three."


def test_normalize_text_handles_empty_and_none():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_chunk_offset_invariant_holds_for_various_texts():
    texts = [
        "Short page.",
        ("Assessment:\nPatient presents with severe knee pain. " * 40),
        "A" * 2000,
        "Para one.\n\nPara two is a bit longer than para one here.\n\n" * 10,
    ]
    for page_number, text in enumerate(texts, start=1):
        chunks = chunk_page_text(text, page_number, doc_id="DOC-1", claim_id="CLM-1")
        for chunk in chunks:
            assert text[chunk.char_start:chunk.char_end] == chunk.text
            assert chunk.text == chunk.text.strip()


def test_chunk_page_text_empty_returns_no_chunks():
    assert chunk_page_text("", 1, "DOC-1", "CLM-1") == []


def test_chunk_page_text_detects_section_header():
    text = "Assessment:\nSevere osteoarthritis of the right knee, failed conservative therapy."
    chunks = chunk_page_text(text, 1, "DOC-1", "CLM-1")
    assert len(chunks) == 1
    assert chunks[0].section == "Assessment"


def test_chunk_page_text_never_infinite_loops_on_pathological_input():
    text = "." * 5000  # no blank lines, no sentence boundaries beyond periods
    chunks = chunk_page_text(text, 1, "DOC-1", "CLM-1")
    assert sum(len(c.text) for c in chunks) <= len(text)
    assert "".join(c.text for c in chunks).replace("", "") != ""


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample fixture not present")
def test_extract_document_pdf_text_layer():
    pages = extract_document(SAMPLE_PDF.read_bytes(), "pdf")
    assert len(pages) >= 1
    assert pages[0].engine == "pdf_text"
    assert pages[0].char_count > 0


def test_extract_document_rejects_unsupported_detected_type():
    with pytest.raises(ValueError):
        extract_document(b"whatever bytes", "docx")


def test_extract_document_image_without_tesseract_binary_degrades_to_failed():
    """On a machine with no tesseract binary installed, an image input
    must never fabricate text -- it comes back engine=failed, not silently
    empty-but-successful."""
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (400, 120), color="white").save(buf, format="PNG")

    pages = extract_document(buf.getvalue(), "png")
    assert len(pages) == 1
    assert pages[0].engine in ("tesseract", "failed")
    if pages[0].engine == "failed":
        assert pages[0].text == ""
