"""
OCR extraction: turns a validated claim document's bytes (already checked
by app.pipeline.ingestion) into per-page text, tagged with which engine
produced it.

`detected_type` comes from the ingestion pipeline's magic-byte sniffing
(app/pipeline/ingestion/checks.py) -- trusted here, never re-derived from
a filename or extension.

Engine order, in keeping with the zero-hallucination rule (never invent
text that isn't really on the page):
  1. A PDF's embedded text layer via pdfplumber -- exact, free, no OCR
     needed. Used whenever a page yields at least MIN_TEXT_CHARS.
  2. Tesseract OCR (pytesseract) for scanned PDF pages, and always for
     standalone images (png/jpeg/tiff), which have no text layer to try
     first. TIFF may carry multiple frames -- each becomes its own page,
     matching claim-documents.page_count's "TIFF: frames" convention.
  3. If Tesseract's binary isn't installed, or OCR yields nothing, the
     page comes back engine="failed" with empty text rather than guessed
     content -- the caller continues with the next page/document either
     way.

Tesseract note: pytesseract only wraps the `tesseract` binary, a separate
OS-level install (not pip) -- see README.md "Known limitations".
"""
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

import pdfplumber
from PIL import Image, ImageSequence

from app.config import settings

MIN_TEXT_CHARS = 20  # below this, a PDF page is treated as scanned/image-only

_WS_RUN_RE = re.compile(r"[ \t]+")


@dataclass
class PageResult:
    page_number: int  # 1-based
    text: str
    engine: str  # "pdf_text" | "tesseract" | "failed"
    ocr_confidence: float | None  # Tesseract mean word confidence (0-100)
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


def normalize_text(text: str) -> str:
    """NFC unicode, CRLF/CR -> LF, collapse horizontal whitespace runs to a
    single space. Line breaks are preserved. Do this exactly once per page:
    every downstream offset (chunking, spans) is computed against this
    normalized text and must never be recomputed against a re-normalized
    copy later."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RUN_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def _ocr_image_via_tesseract(image) -> tuple[str, float | None] | None:
    """Returns (text, mean_confidence), or None if Tesseract itself is
    unavailable (package not installed or binary missing) -- distinct from
    a successful run that just found no text."""
    try:
        import pytesseract
    except ImportError:
        return None

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    try:
        text = pytesseract.image_to_string(image)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return None

    confidences = [float(c) for c in data["conf"] if str(c) not in ("-1", "")]
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return text, mean_conf


def _extract_pdf(data: bytes) -> list[PageResult]:
    try:
        pdf = pdfplumber.open(BytesIO(data))
    except Exception:
        return [PageResult(1, "", "failed", None)]

    pages: list[PageResult] = []
    with pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = normalize_text(page.extract_text() or "")
            if len(text.strip()) >= MIN_TEXT_CHARS:
                pages.append(PageResult(i, text, "pdf_text", None))
                continue

            ocr_result = None
            if settings.ocr_provider == "tesseract":
                image = page.to_image(resolution=200).original
                ocr_result = _ocr_image_via_tesseract(image)

            if ocr_result is None:
                pages.append(PageResult(i, "", "failed", None))
            else:
                ocr_text, confidence = ocr_result
                pages.append(PageResult(i, normalize_text(ocr_text), "tesseract", confidence))
    return pages


def _extract_image_frames(data: bytes) -> list[PageResult]:
    """PNG/JPEG always have one frame; TIFF may have several -- each frame
    becomes its own page, same as claim-documents.page_count already
    counts them."""
    if settings.ocr_provider != "tesseract":
        try:
            with Image.open(BytesIO(data)) as img:
                frame_count = getattr(img, "n_frames", 1)
        except Exception:
            frame_count = 1
        return [PageResult(i, "", "failed", None) for i in range(1, frame_count + 1)]

    try:
        image = Image.open(BytesIO(data))
    except Exception:
        return [PageResult(1, "", "failed", None)]

    pages: list[PageResult] = []
    with image:
        for i, frame in enumerate(ImageSequence.Iterator(image), start=1):
            ocr_result = _ocr_image_via_tesseract(frame.convert("RGB"))
            if ocr_result is None:
                pages.append(PageResult(i, "", "failed", None))
            else:
                text, confidence = ocr_result
                pages.append(PageResult(i, normalize_text(text), "tesseract", confidence))
    return pages


def extract_document(data: bytes, detected_type: str) -> list[PageResult]:
    """`detected_type`: "pdf" | "png" | "jpeg" | "tiff", from
    app.pipeline.ingestion.checks.detect_type -- trust this rather than
    re-sniffing. Returns one PageResult per PDF page or image frame. A
    page that can't be read comes back engine="failed" rather than
    raising, so one bad page never aborts the rest of the document."""
    if detected_type == "pdf":
        return _extract_pdf(data)
    if detected_type in ("png", "jpeg", "tiff"):
        return _extract_image_frames(data)
    raise ValueError(f"Unsupported detected_type: {detected_type!r}")
