/**
 * Documents uploaded to a claim (GET /claims/{id}/documents), with an
 * "Add documents" button for claims that are still open. Validation
 * happens in the backend ingestion stage; files it refuses come back in
 * `rejected` with a reason, shown via RejectedList.
 */
"use client";

import { useEffect, useState } from "react";
import { FileText, Image as ImageIcon, Loader2, Paperclip, Plus, XCircle } from "lucide-react";

export type Rejected = { filename: string; code: string; message: string };

type ClaimDocument = {
  doc_id: string;
  original_filename: string;
  detected_type: string;
  doc_type: string;
  size_bytes: number;
  page_count: number | null;
  source_uri: string;
  ocr_status: string;
  warnings: string[];
  uploaded_at: string;
};

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff";
const OPEN_STATUSES = ["DRAFT", "PENDING", "REQUEST_INFO"];

export default function DocumentsPanel({
  claimId,
  claimStatus,
  apiBaseUrl,
  onClaimChanged,
}: {
  claimId: string;
  claimStatus: string;
  apiBaseUrl: string;
  onClaimChanged?: (claim: any) => void;
}) {
  const [docs, setDocs] = useState<ClaimDocument[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<Rejected[]>([]);

  async function load() {
    try {
      const res = await fetch(`${apiBaseUrl}/claims/${claimId}/documents`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `Failed to load documents (${res.status})`);
      setDocs(body);
      setLoadError(null);
    } catch (err: any) {
      setLoadError(err.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claimId]);

  async function upload(list: FileList | null) {
    if (!list || list.length === 0) return;
    setUploading(true);
    setUploadError(null);
    setRejected([]);

    const fd = new FormData();
    for (const file of Array.from(list)) fd.append("files", file);
    try {
      const res = await fetch(`${apiBaseUrl}/claims/${claimId}/documents`, { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      setRejected(body.rejected || []);
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Upload failed (${res.status})`);
      onClaimChanged?.(body.claim);
      await load();
    } catch (err: any) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  const canUpload = OPEN_STATUSES.includes((claimStatus || "").toUpperCase());

  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <Paperclip size={15} /> Documents {docs && <span className="font-normal text-slate-400">({docs.length})</span>}
        </h2>
        {canUpload && (
          <label
            className={`flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 ${
              uploading ? "pointer-events-none opacity-60" : ""
            }`}
          >
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            {uploading ? "Uploading..." : "Add documents"}
            <input
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                upload(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        )}
      </div>

      {loadError && <p className="text-sm text-red-600">{loadError}</p>}
      {!docs && !loadError && <p className="text-sm text-slate-400">Loading documents...</p>}
      {docs && docs.length === 0 && <p className="text-sm text-slate-400">No documents uploaded for this claim.</p>}

      {docs && docs.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {docs.map((d) => (
            <li key={d.doc_id} className="flex items-center justify-between py-2.5 text-sm">
              <div className="flex min-w-0 items-center gap-2.5">
                {d.detected_type === "pdf" ? (
                  <FileText size={16} className="shrink-0 text-red-500" />
                ) : (
                  <ImageIcon size={16} className="shrink-0 text-blue-500" />
                )}
                <div className="min-w-0">
                  <a
                    href={`${apiBaseUrl}${d.source_uri}`}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate font-medium text-slate-800 hover:text-blue-600 hover:underline"
                  >
                    {d.original_filename}
                  </a>
                  <div className="text-xs text-slate-400">
                    {d.doc_id} · {d.doc_type.replace(/_/g, " ")} · {d.detected_type.toUpperCase()} ·{" "}
                    {d.page_count ?? "?"} page{d.page_count === 1 ? "" : "s"} · {formatBytes(d.size_bytes)}
                  </div>
                  {d.warnings?.length > 0 && (
                    <div className="text-xs text-amber-600">{d.warnings.join(", ")}</div>
                  )}
                </div>
              </div>
              <span className={`badge ${d.ocr_status === "DONE" ? "badge-approved" : d.ocr_status === "FAILED" ? "badge-denied" : "badge-info"}`}>
                OCR {d.ocr_status.toLowerCase()}
              </span>
            </li>
          ))}
        </ul>
      )}

      {uploadError && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
          {uploadError}
        </p>
      )}
      {rejected.length > 0 && (
        <div className="mt-3">
          <RejectedList rejected={rejected} />
        </div>
      )}
    </div>
  );
}

export function RejectedList({ rejected }: { rejected: Rejected[] }) {
  return (
    <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-inset ring-amber-600/20">
      <div className="mb-1 font-medium">
        {rejected.length} file{rejected.length > 1 ? "s were" : " was"} not accepted:
      </div>
      <ul className="space-y-0.5">
        {rejected.map((r, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <XCircle size={14} className="mt-0.5 shrink-0" />
            <span>
              <span className="font-medium">{r.filename}</span> — {r.message}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
