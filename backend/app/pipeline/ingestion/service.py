"""
Ingestion stage: hospital uploads documents → validated, stored,
registered, claim in DRAFT.

    screen   batch limits → per-file checks (checks.py) → duplicate checks
    commit   store bytes → index claim-documents → attach to the claim
             (rolled back if any write fails)
    record   ledger: CLAIM_CREATED / STATUS_CHANGED / DOCUMENT_UPLOADED

Valid files are accepted even if others in the same batch are rejected;
each rejection comes back with a reason code. If nothing is valid the
request fails and nothing is stored (and for intake, no claim is made).

Ledger events are written only after the data commit succeeds, so the
chain never describes a document that was rolled back.
"""
import uuid
from datetime import datetime, timezone

from app.indices.names import CLAIM_FILES
from app.pipeline.ingestion.checks import inspect_file
from app.pipeline.ingestion.models import (
    DOC_TYPES,
    UPLOADABLE_STATUSES,
    CheckFailed,
    ClaimDetails,
    ClaimIntake,
    FileInspection,
    IncomingFile,
    IngestionError,
    IngestionResult,
    Limits,
    RejectedFile,
)

Screened = list[tuple[IncomingFile, FileInspection]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _flat_fields(details: ClaimDetails | None) -> dict:
    """Top-level fields the frontend claim views read (hospital/claims/[id])."""
    if details is None:
        return {}
    d = details.model_dump(mode="json")
    patient, clinical = d.get("patient") or {}, d.get("clinical") or {}
    admission, hospital = d.get("admission") or {}, d.get("hospital") or {}
    insurance = d.get("insurance") or {}
    flat = {
        "patient_name": patient.get("name"),
        "patient_age": patient.get("age"),
        "patient_gender": patient.get("gender"),
        "admission_date": admission.get("admission_date"),
        "discharge_date": admission.get("discharge_date"),
        "department": hospital.get("department"),
        "attending_physician": hospital.get("attending_doctor"),
        "hospital": hospital.get("name"),
        "diagnosis_description": clinical.get("diagnosis_in_words"),
        "procedure_name": clinical.get("procedures"),
        "policy_id": insurance.get("policy_number"),
    }
    return {k: v for k, v in flat.items() if v is not None}


class IngestionService:
    def __init__(self, repository, blob_store, limits: Limits):
        self.repo = repository
        self.blobs = blob_store
        self.limits = limits

    # ── public API ────────────────────────────────────────────────────

    def intake(
        self,
        meta: ClaimIntake,
        files: list[IncomingFile],
        doc_type: str = "supporting_document",
    ) -> IngestionResult:
        """New claim from a document upload. Claim starts in DRAFT."""
        self._check_doc_type(doc_type)
        claim_id = meta.claim_id or _new_id("CLM")
        if self.repo.find_claim(claim_id):
            raise IngestionError(409, "claim_exists", f"Claim {claim_id} already exists.")

        # Documents are optional at intake (the hospital form can be sent
        # without any); if files were sent, at least one must pass.
        accepted, rejected = self._screen(files, claim_id) if files else ([], [])
        if files and not accepted:
            raise IngestionError(422, "no_valid_files", "None of the uploaded files passed validation.", rejected)

        details = meta.details
        claim = {
            "claim_id": claim_id,
            "patient_id": meta.patient_id,
            "payer_name": meta.payer_name,
            "cpt_code": None,
            "icd10_code": None,
            "claim_amount": meta.claim_amount or (meta.details.estimated_total_cost if meta.details else None),
            "claim_type": meta.claim_type,
            "submitted_date": _now(),
            "submitted_by": meta.submitted_by,
            "status": "DRAFT",
            "source": "intake",
            "details": details.model_dump(mode="json", exclude_none=True) if details else {},
            # Flat copies of the details the hospital/insurance claim views read.
            **_flat_fields(details),
            "attached_documents": [],
        }
        es_id = self.repo.create_claim(claim)
        try:
            docs = self._commit(claim, CLAIM_FILES, es_id, accepted, doc_type, meta.submitted_by)
        except Exception:
            self.repo.delete_claim(es_id)
            raise

        self.repo.record_event(claim_id, "CLAIM_CREATED", {
            "patient_id": claim["patient_id"],
            "payer_name": claim["payer_name"],
            "claim_type": claim["claim_type"],
            "source": "intake",
            "submitted_by": meta.submitted_by,
        })
        self._record_uploads(claim_id, docs)
        return IngestionResult({"id": es_id, **claim}, docs, rejected, created_claim=True)

    def add_documents(
        self,
        claim_id: str,
        files: list[IncomingFile],
        doc_type: str = "supporting_document",
        uploaded_by: str = "unknown",
    ) -> IngestionResult:
        """More documents for an existing, still-open claim."""
        self._check_doc_type(doc_type)
        hit = self.repo.find_claim(claim_id)
        if not hit:
            raise IngestionError(404, "claim_not_found", "Claim not found.")
        index, es_id, claim = hit["_index"], hit["_id"], hit["_source"]

        status = claim.get("status")
        if status not in UPLOADABLE_STATUSES:
            raise IngestionError(
                409, "claim_not_open",
                f"Claim is {status}; documents can only be added while it is "
                f"{', '.join(sorted(UPLOADABLE_STATUSES))}.",
            )

        accepted, rejected = self._screen(files, claim_id)
        if not accepted:
            raise IngestionError(422, "no_valid_files", "None of the uploaded files passed validation.", rejected)

        # New evidence reopens a claim that was waiting on more info.
        reopened = status == "REQUEST_INFO"
        if reopened:
            claim["status"] = "DRAFT"
        docs = self._commit(claim, index, es_id, accepted, doc_type, uploaded_by)

        if reopened:
            self.repo.record_event(claim_id, "STATUS_CHANGED", {
                "from": "REQUEST_INFO", "to": "DRAFT", "reason": "documents_added",
            })
        self._record_uploads(claim_id, docs)
        return IngestionResult({"id": es_id, **claim}, docs, rejected, created_claim=False)

    def list_documents(self, claim_id: str) -> list[dict]:
        if not self.repo.find_claim(claim_id):
            raise IngestionError(404, "claim_not_found", "Claim not found.")
        return self.repo.list_documents(claim_id)

    # ── screen ────────────────────────────────────────────────────────

    def _screen(self, files: list[IncomingFile], claim_id: str) -> tuple[Screened, list[RejectedFile]]:
        if not files:
            raise IngestionError(422, "no_files", "No files were uploaded.")
        if len(files) > self.limits.max_files_per_upload:
            raise IngestionError(
                422, "too_many_files",
                f"{len(files)} files uploaded; the limit is {self.limits.max_files_per_upload} per request.",
            )

        accepted: Screened = []
        rejected: list[RejectedFile] = []
        seen_in_batch: dict[str, str] = {}

        for file in files:
            try:
                info = inspect_file(file, self.limits)
            except CheckFailed as e:
                rejected.append(RejectedFile(file.filename, e.code, e.message))
                continue
            if info.sha256 in seen_in_batch:
                rejected.append(RejectedFile(
                    file.filename, "duplicate_in_upload",
                    f"Same content as '{seen_in_batch[info.sha256]}' in this upload.",
                ))
                continue
            seen_in_batch[info.sha256] = info.safe_filename
            accepted.append((file, info))

        existing = self.repo.find_documents_by_sha256([info.sha256 for _, info in accepted])
        on_this_claim = {d["sha256"]: d["doc_id"] for d in existing if d["claim_id"] == claim_id}
        elsewhere: dict[str, set[str]] = {}
        for d in existing:
            if d["claim_id"] != claim_id:
                elsewhere.setdefault(d["sha256"], set()).add(d["claim_id"])

        still_accepted: Screened = []
        for file, info in accepted:
            if info.sha256 in on_this_claim:
                rejected.append(RejectedFile(
                    file.filename, "duplicate_on_claim",
                    f"Already attached to this claim as {on_this_claim[info.sha256]}.",
                ))
                continue
            # Not an error (a referral letter can legitimately back two
            # claims) but worth surfacing to reviewers.
            for other in sorted(elsewhere.get(info.sha256, ())):
                info.warnings.append(f"also_attached_to:{other}")
            still_accepted.append((file, info))

        return still_accepted, rejected

    # ── commit ────────────────────────────────────────────────────────

    def _commit(
        self, claim: dict, index: str, es_id: str, accepted: Screened, doc_type: str, uploaded_by: str
    ) -> list[dict]:
        claim_id = claim["claim_id"]
        stored_uris: list[str] = []
        indexed_ids: list[str] = []
        docs: list[dict] = []
        try:
            for file, info in accepted:
                doc_id = _new_id("DOC")
                uri = self.blobs.put(claim_id, doc_id, info.extension, file.data)
                stored_uris.append(uri)
                doc = {
                    "doc_id": doc_id,
                    "claim_id": claim_id,
                    "original_filename": info.safe_filename,
                    "extension": info.extension,
                    "detected_type": info.detected_type,
                    "client_mime_type": file.client_mime_type,
                    "size_bytes": info.size_bytes,
                    "sha256": info.sha256,
                    "source_uri": uri,
                    "doc_type": doc_type,
                    "page_count": info.page_count,
                    "image_width": info.image_width,
                    "image_height": info.image_height,
                    "ocr_status": "PENDING",
                    "warnings": info.warnings,
                    "uploaded_at": _now(),
                    "uploaded_by": uploaded_by,
                }
                self.repo.index_document(doc)
                indexed_ids.append(doc_id)
                docs.append(doc)

            claim.setdefault("attached_documents", []).extend(
                {"doc_id": d["doc_id"], "doc_type": d["doc_type"], "source_uri": d["source_uri"]}
                for d in docs
            )
            self.repo.update_claim(index, es_id, claim)
        except Exception:
            for doc_id in indexed_ids:
                self._quietly(self.repo.delete_document, doc_id)
            for uri in stored_uris:
                self._quietly(self.blobs.delete, uri)
            raise
        return docs

    # ── record ────────────────────────────────────────────────────────

    def _record_uploads(self, claim_id: str, docs: list[dict]) -> None:
        for doc in docs:
            self.repo.record_event(claim_id, "DOCUMENT_UPLOADED", {
                "doc_id": doc["doc_id"],
                "sha256": doc["sha256"],
                "size_bytes": doc["size_bytes"],
                "detected_type": doc["detected_type"],
                "original_filename": doc["original_filename"],
                "source_uri": doc["source_uri"],
                "uploaded_by": doc["uploaded_by"],
            }, ref_id=doc["doc_id"])

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _check_doc_type(doc_type: str) -> None:
        if doc_type not in DOC_TYPES:
            raise IngestionError(
                422, "invalid_doc_type",
                f"doc_type must be one of: {', '.join(sorted(DOC_TYPES))}.",
            )

    @staticmethod
    def _quietly(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 - best-effort rollback; the original error is re-raised
            pass
