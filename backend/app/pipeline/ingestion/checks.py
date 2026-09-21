"""
Per-file validation checks for uploaded claim documents.

Each check is a plain function `(file, info, limits) -> None` that either
records facts on `info` or raises CheckFailed(code, message). FILE_CHECKS
runs them in order and stops at the first failure, so later checks can
rely on earlier ones (e.g. check_pdf only runs on bytes already sniffed
as a PDF). Adding a check = write a function, append it to FILE_CHECKS.

The file's real type comes from its magic bytes, never from the client's
Content-Type header or the extension alone — a renamed executable must
not get through because it is called "scan.pdf".

Batch-level checks (file count, duplicates across files and against
documents already on the claim) live in service.py because they need
more than one file or the database.
"""
import hashlib
import io
import re
import warnings
from pathlib import PurePosixPath, PureWindowsPath

import pdfplumber
from PIL import Image

from app.pipeline.ingestion.models import (
    ALLOWED_EXTENSIONS,
    CheckFailed,
    FileInspection,
    IncomingFile,
    Limits,
)

_MAX_FILENAME_LEN = 255

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
]

# PDF actions that run code or open other programs. A scanned referral
# letter or lab report has no business containing these. Best-effort:
# keys inside compressed object streams are not visible to a byte scan.
_PDF_ACTIVE_CONTENT_RE = re.compile(rb"/(JavaScript|JS|Launch)(?![A-Za-z0-9])")

_PIL_FORMATS = {"png": "PNG", "jpeg": "JPEG", "tiff": "TIFF"}


def detect_type(data: bytes) -> str | None:
    """Content type from magic bytes, or None if not an accepted type."""
    # Some PDF writers put junk before the header; the spec allows it
    # within the first 1024 bytes.
    if b"%PDF-" in data[:1024]:
        return "pdf"
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            return kind
    return None


def check_filename(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    # Keep only the final path component whatever separator the client
    # used; the stored file is renamed to its doc_id anyway, the original
    # name is metadata only.
    name = PureWindowsPath(PurePosixPath(file.filename or "").name).name.strip()
    if not name or name in {".", ".."}:
        raise CheckFailed("invalid_filename", "File has no usable name.")
    if "\x00" in name:
        raise CheckFailed("invalid_filename", "File name contains a NUL byte.")
    if len(name) > _MAX_FILENAME_LEN:
        raise CheckFailed("invalid_filename", f"File name is longer than {_MAX_FILENAME_LEN} characters.")
    info.safe_filename = name


def check_extension(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    ext = PurePosixPath(info.safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise CheckFailed(
            "unsupported_extension",
            f"'{ext or '(none)'}' files are not accepted. Allowed: {allowed}.",
        )
    info.extension = ext


def check_size(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    if file.truncated or len(file.data) > limits.max_file_bytes:
        mb = limits.max_file_bytes // (1024 * 1024)
        raise CheckFailed("file_too_large", f"File is larger than the {mb} MB limit.")
    if len(file.data) == 0:
        raise CheckFailed("empty_file", "File is empty.")
    info.size_bytes = len(file.data)
    info.sha256 = hashlib.sha256(file.data).hexdigest()


def check_signature(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    detected = detect_type(file.data)
    if detected is None:
        raise CheckFailed(
            "unrecognized_content",
            "File content is not a PDF, PNG, JPEG or TIFF, whatever its extension says.",
        )
    expected = ALLOWED_EXTENSIONS[info.extension]
    if detected != expected:
        raise CheckFailed(
            "extension_mismatch",
            f"File is named '{info.extension}' but its content is {detected.upper()}.",
        )
    info.detected_type = detected
    if file.client_mime_type and detected not in file.client_mime_type.lower():
        # Browsers send odd types (application/octet-stream, image/jpg);
        # the bytes are the source of truth, this is just recorded.
        info.warnings.append(f"client_mime_mismatch:{file.client_mime_type}")


def check_pdf(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    if info.detected_type != "pdf":
        return
    if _PDF_ACTIVE_CONTENT_RE.search(file.data):
        raise CheckFailed(
            "pdf_active_content",
            "PDF contains JavaScript or launch actions, which are not accepted.",
        )
    try:
        with pdfplumber.open(io.BytesIO(file.data)) as pdf:
            page_count = len(pdf.pages)
    except Exception as e:  # noqa: BLE001 - pdfminer raises a wide range of types
        if _is_password_error(e):
            raise CheckFailed(
                "pdf_encrypted",
                "PDF is password-protected. Upload an unlocked copy.",
            ) from e
        raise CheckFailed("pdf_unreadable", "PDF is damaged or could not be parsed.") from e

    if page_count == 0:
        raise CheckFailed("pdf_no_pages", "PDF has no pages.")
    if page_count > limits.max_pdf_pages:
        raise CheckFailed(
            "pdf_too_many_pages",
            f"PDF has {page_count} pages; the limit is {limits.max_pdf_pages}.",
        )
    info.page_count = page_count


def check_image(file: IncomingFile, info: FileInspection, limits: Limits) -> None:
    if info.detected_type not in _PIL_FORMATS:
        return
    try:
        with warnings.catch_warnings():
            # Pillow only warns between 1x and 2x MAX_IMAGE_PIXELS; treat
            # that as a rejection too rather than decoding a pixel bomb.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(file.data)) as img:
                img.verify()
            # verify() leaves the image unusable; reopen for metadata.
            with Image.open(io.BytesIO(file.data)) as img:
                fmt = img.format
                width, height = img.size
                frames = getattr(img, "n_frames", 1)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise CheckFailed("image_too_many_pixels", "Image dimensions are too large to process safely.") from e
    except Exception as e:  # noqa: BLE001 - Pillow raises many types for bad data
        raise CheckFailed("image_unreadable", "Image is damaged or could not be decoded.") from e

    if fmt != _PIL_FORMATS[info.detected_type]:
        raise CheckFailed("image_unreadable", f"Image decoded as {fmt}, expected {info.detected_type.upper()}.")
    if min(width, height) < limits.min_image_side_px:
        raise CheckFailed(
            "image_too_small",
            f"Image is {width}x{height}px; the shorter side must be at least "
            f"{limits.min_image_side_px}px for OCR.",
        )
    info.image_width, info.image_height = width, height
    info.page_count = frames


FILE_CHECKS = [
    check_filename,
    check_extension,
    check_size,
    check_signature,
    check_pdf,
    check_image,
]


def inspect_file(file: IncomingFile, limits: Limits, checks=FILE_CHECKS) -> FileInspection:
    """Runs every check in order. Raises CheckFailed on the first failure."""
    info = FileInspection()
    for check in checks:
        check(file, info, limits)
    return info


def _is_password_error(exc: BaseException) -> bool:
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if "Password" in type(exc).__name__ or "password" in str(exc).lower():
            return True
        for arg in getattr(exc, "args", ()):
            if isinstance(arg, BaseException) and _is_password_error(arg):
                return True
        exc = exc.__cause__ or exc.__context__
    return False
