"""
Blob storage for uploaded claim documents.

LocalBlobStore writes under backend/uploads/{claim_id}/{doc_id}{ext},
served back out by the /files static mount in main.py. Files are
write-once: the sha256 recorded at ingestion (and in the audit ledger)
must keep matching the bytes on disk, so put() refuses to overwrite.

Swapping to S3 is a new class with the same three methods (boto3 is
already a dependency); nothing above this module knows where bytes live.
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from app.config import settings

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def upload_root() -> Path:
    if settings.upload_dir:
        return Path(settings.upload_dir)
    return Path(__file__).resolve().parents[3] / "uploads"


class BlobStore(Protocol):
    def put(self, claim_id: str, doc_id: str, extension: str, data: bytes) -> str:
        """Stores bytes, returns the source_uri clients use to fetch them."""

    def delete(self, source_uri: str) -> None: ...

    def read(self, source_uri: str) -> bytes: ...


class LocalBlobStore:
    URI_PREFIX = "/files/"

    def __init__(self, root: Path | None = None):
        self.root = (root or upload_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, claim_id: str, doc_id: str, extension: str, data: bytes) -> str:
        for segment in (claim_id, doc_id):
            if not _SAFE_SEGMENT_RE.match(segment):
                raise ValueError(f"Unsafe path segment: {segment!r}")
        claim_dir = self.root / claim_id
        claim_dir.mkdir(parents=True, exist_ok=True)
        dest = claim_dir / f"{doc_id}{extension}"
        if dest.exists():
            raise FileExistsError(f"{dest} already exists; stored documents are write-once")

        # Write to a temp file in the same directory, then rename, so a
        # crash mid-write never leaves a partial file under the real name.
        fd, tmp = tempfile.mkstemp(dir=claim_dir, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.link(tmp, dest)  # fails if dest appeared meanwhile, unlike rename
        finally:
            os.unlink(tmp)
        return f"{self.URI_PREFIX}{claim_id}/{dest.name}"

    def delete(self, source_uri: str) -> None:
        self._path(source_uri).unlink(missing_ok=True)

    def read(self, source_uri: str) -> bytes:
        return self._path(source_uri).read_bytes()

    def _path(self, source_uri: str) -> Path:
        if not source_uri.startswith(self.URI_PREFIX):
            raise ValueError(f"Not a local blob URI: {source_uri!r}")
        path = (self.root / source_uri[len(self.URI_PREFIX):]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"URI escapes the upload root: {source_uri!r}")
        return path
