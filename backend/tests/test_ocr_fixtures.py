"""
Regression tests against the realistic fixtures in
data/sample/documents/ (see manifest.json there for what's real vs
fabricated in each file) -- a clinical note and a hospital bill, each as a
real-text PDF, a rendered image, and an image-only ("scanned") PDF.

`detected_type` is derived the same way the real ingestion pipeline does
(app.pipeline.ingestion.checks.detect_type, magic bytes) rather than
hardcoded, so these tests exercise the exact contract OCR receives from
intake in production.

The Tesseract-dependent cases are skipped, not failed, when the tesseract
binary isn't installed on the machine running the tests -- consistent
with extract.py's own "degrade to FAILED, don't fabricate" rule; this
file just avoids treating an environment gap as a code regression.
"""
import shutil
from pathlib import Path

import pytest

from app.pipeline.ingestion.checks import detect_type
from app.pipeline.ocr.extract import PageResult, extract_document
from app.pipeline.ocr.service import OCRService

DOCS_DIR = Path(__file__).parent.parent.parent / "data" / "sample" / "documents"

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None

CLINICAL_NOTE_MARKERS = ["chronic lower back pain", "L4-L5", "Gabapentin", "62323", "M51.36"]
HOSPITAL_BILL_MARKERS = ["99213", "62323", "72100", "875.00"]


def _read(name: str) -> tuple[bytes, str]:
    data = (DOCS_DIR / name).read_bytes()
    return data, detect_type(data)


def _assert_offset_invariant(page_docs, chunk_docs):
    pages_by_number = {p["page_number"]: p["text"] for p in page_docs}
    for chunk in chunk_docs:
        assert pages_by_number[chunk["page_number"]][chunk["char_start"]:chunk["char_end"]] == chunk["text"]


@pytest.mark.skipif(not DOCS_DIR.exists(), reason="fixtures not present")
def test_clinical_note_pdf_text_layer_extracts_key_facts():
    data, kind = _read("clinical_note.pdf")
    assert kind == "pdf"
    pages = extract_document(data, kind)
    assert pages[0].engine == "pdf_text"
    for marker in CLINICAL_NOTE_MARKERS:
        assert marker in pages[0].text


@pytest.mark.skipif(not DOCS_DIR.exists(), reason="fixtures not present")
def test_hospital_bill_pdf_text_layer_extracts_line_items():
    data, kind = _read("hospital_bill.pdf")
    pages = extract_document(data, kind)
    assert pages[0].engine == "pdf_text"
    for marker in HOSPITAL_BILL_MARKERS:
        assert marker in pages[0].text


@pytest.mark.skipif(not DOCS_DIR.exists(), reason="fixtures not present")
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract binary not installed")
def test_clinical_note_image_ocr_extracts_key_facts():
    data, kind = _read("clinical_note.png")
    assert kind == "png"
    pages = extract_document(data, kind)
    assert pages[0].engine == "tesseract"
    assert pages[0].ocr_confidence > 50
    # Real-OCR text, not exact -- assert on markers unaffected by the
    # known digit/'@' misread rather than full-string equality.
    for marker in ["chronic lower back pain", "L4-L5", "Gabapentin", "62323"]:
        assert marker in pages[0].text


@pytest.mark.skipif(not DOCS_DIR.exists(), reason="fixtures not present")
@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract binary not installed")
def test_scanned_pdf_falls_back_to_tesseract_within_pdf():
    """The image-only PDF has no text layer at all -- extract.py must
    detect that inside pdfplumber and route the rendered page to
    Tesseract, the same path a real scanned upload would take."""
    data, kind = _read("scanned_clinical_note.pdf")
    assert kind == "pdf"
    pages = extract_document(data, kind)
    assert pages[0].engine == "tesseract"
    for marker in ["chronic lower back pain", "Gabapentin"]:
        assert marker in pages[0].text


def test_image_without_tesseract_never_fabricates_text(monkeypatch):
    """Simulates a machine with no OCR provider configured: must degrade
    to FAILED/empty text, never invent plausible-looking content."""
    import app.pipeline.ocr.extract as extract_module
    monkeypatch.setattr(extract_module.settings, "ocr_provider", "none")

    data, kind = _read("clinical_note.png") if DOCS_DIR.exists() else (None, None)
    if data is None:
        pytest.skip("fixtures not present")

    pages = extract_document(data, kind)
    assert pages[0].engine == "failed"
    assert pages[0].text == ""


# ── service-level: idempotent re-processing + zero-vector skip ──────────

class _FakeRepository:
    """In-memory stand-in for OCRRepository -- no Elasticsearch needed to
    test the service's control flow (delete-before-rewrite, status
    updates, ledger events)."""

    def __init__(self, documents: dict[str, dict], blobs: dict[str, bytes]):
        self._documents = documents
        self._blobs = blobs
        self.pages: list[dict] = []
        self.chunks: list[dict] = []
        self.cleared: list[str] = []
        self.status_updates: list[tuple[str, dict]] = []
        self.events: list[tuple[str, str, dict]] = []

    def find_pending_documents(self, claim_id):
        return [d for d in self._documents.values() if d["claim_id"] == claim_id and d["ocr_status"] == "PENDING"]

    def read_bytes(self, source_uri):
        return self._blobs[source_uri]

    def clear_previous_output(self, doc_id):
        self.cleared.append(doc_id)
        self.pages = [p for p in self.pages if p["doc_id"] != doc_id]
        self.chunks = [c for c in self.chunks if c["doc_id"] != doc_id]

    def index_pages(self, pages):
        self.pages.extend(pages)

    def index_chunks(self, chunks):
        self.chunks.extend(chunks)

    def update_document_status(self, doc_id, **fields):
        self.status_updates.append((doc_id, fields))

    def record_event(self, claim_id, event_type, payload, ref_id=None):
        self.events.append((claim_id, event_type, payload))
        return {}


@pytest.mark.skipif(not DOCS_DIR.exists(), reason="fixtures not present")
def test_process_document_clears_old_output_before_rewriting():
    data = (DOCS_DIR / "clinical_note.pdf").read_bytes()
    doc = {
        "doc_id": "DOC-1", "claim_id": "CLM-1", "source_uri": "/files/CLM-1/DOC-1.pdf",
        "detected_type": "pdf", "ocr_status": "PENDING",
    }
    repo = _FakeRepository({"DOC-1": doc}, {"/files/CLM-1/DOC-1.pdf": data})
    service = OCRService(repo)

    result = service.process_document(doc)

    assert result["ocr_status"] == "DONE"
    assert repo.cleared == ["DOC-1"]
    assert len(repo.pages) == result["page_count"]
    assert repo.status_updates[-1] == ("DOC-1", {
        "ocr_status": "DONE", "page_count": result["page_count"], "ocr_engine": "pdf_text",
    })
    assert repo.events[-1][1] == "OCR_COMPLETED"
    _assert_offset_invariant(repo.pages, repo.chunks)


def test_process_document_reports_failed_without_crashing_the_batch():
    doc = {
        "doc_id": "DOC-MISSING", "claim_id": "CLM-1", "source_uri": "/files/CLM-1/nope.pdf",
        "detected_type": "pdf", "ocr_status": "PENDING",
    }
    repo = _FakeRepository({"DOC-MISSING": doc}, {})  # read_bytes will KeyError
    service = OCRService(repo)

    result = service.process_document(doc)

    assert result["ocr_status"] == "FAILED"
    assert repo.status_updates == [("DOC-MISSING", {"ocr_status": "FAILED"})]
    assert repo.events[-1][1] == "OCR_COMPLETED"


def test_build_pages_and_chunks_omits_vector_for_all_zero_embedding(monkeypatch):
    import app.pipeline.ocr.service as service_module
    monkeypatch.setattr(service_module, "embed_text", lambda text: [0.0] * 768)

    page_docs, chunk_docs = OCRService._build_pages_and_chunks(
        "DOC-1", "CLM-1",
        [PageResult(1, "Some real chunk text here.", "pdf_text", None)],
    )
    assert chunk_docs, "expected at least one chunk"
    for chunk in chunk_docs:
        assert "text_vector" not in chunk
