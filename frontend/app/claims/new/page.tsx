"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { RejectedList, formatBytes, type Rejected } from "../../components/DocumentsPanel";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// Mirrors ALLOWED_EXTENSIONS in backend app/pipeline/ingestion/models.py.
// The backend re-checks everything; this only saves a round trip.
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff";

const DOC_TYPES = [
  ["supporting_document", "Supporting document"],
  ["referral_letter", "Referral letter"],
  ["op_note", "Operative note"],
  ["discharge_summary", "Discharge summary"],
  ["lab_report", "Lab report"],
  ["prescription", "Prescription"],
  ["imaging_report", "Imaging report"],
  ["other", "Other"],
] as const;

type FormState = {
  claim_id: string;
  patient_id: string;
  payer_name: string;
  claim_type: string;
  doc_type: string;
};

type StoredDocument = {
  doc_id: string;
  original_filename: string;
  doc_type: string;
  detected_type: string;
  size_bytes: number;
  page_count: number | null;
  sha256: string;
  source_uri: string;
  warnings: string[];
};

type IntakeResult = {
  claim: { claim_id: string; status: string; patient_id: string; payer_name: string };
  accepted: StoredDocument[];
  rejected: Rejected[];
};

const EMPTY: FormState = {
  claim_id: "",
  patient_id: "",
  payer_name: "",
  claim_type: "professional",
  doc_type: "supporting_document",
};

export default function NewClaimPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<Rejected[]>([]);
  const [result, setResult] = useState<IntakeResult | null>(null);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    // Copy now: the caller resets the input right after, which empties this
    // live FileList before React may get round to running the updater.
    const picked = Array.from(list);
    setError(null);
    setFiles((prev) => [...prev, ...picked]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setRejected([]);

    if (!form.patient_id.trim() || !form.payer_name.trim()) {
      setError("Patient ID and payer are required.");
      return;
    }
    if (files.length === 0) {
      setError("Attach at least one document first.");
      return;
    }

    const fd = new FormData();
    fd.append("patient_id", form.patient_id.trim());
    fd.append("payer_name", form.payer_name.trim());
    fd.append("claim_type", form.claim_type);
    fd.append("doc_type", form.doc_type);
    if (form.claim_id.trim()) fd.append("claim_id", form.claim_id.trim());
    for (const file of files) fd.append("files", file);

    setSubmitting(true);
    try {
      let res: Response;
      try {
        res = await fetch(`${API_BASE_URL}/claims/intake`, { method: "POST", body: fd });
      } catch {
        throw new Error(`Could not reach the API at ${API_BASE_URL}. Is the backend running?`);
      }
      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        setRejected(body.rejected || []);
        throw new Error(typeof body.detail === "string" ? body.detail : `Upload failed (${res.status})`);
      }
      setResult(body as IntakeResult);
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return <UploadSummary result={result} onOpen={() => router.push(`/claims/${result.claim.claim_id}`)} />;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <Link href="/claims" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft size={14} />
          Back to Claims
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">Upload Claim Documents</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload the hospital's documents. A draft claim is created from them; codes are filled in from the documents
          in the next steps.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card space-y-5 p-6">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Patient ID" required>
            <input
              value={form.patient_id}
              onChange={(e) => update("patient_id", e.target.value)}
              placeholder="PAT-883910"
              className="input"
            />
          </Field>
          <Field label="Payer" required>
            <input
              value={form.payer_name}
              onChange={(e) => update("payer_name", e.target.value)}
              placeholder="UnitedHealthcare"
              className="input"
            />
          </Field>
          <Field label="Claim type">
            <select value={form.claim_type} onChange={(e) => update("claim_type", e.target.value)} className="input">
              <option value="professional">Professional</option>
              <option value="institutional">Institutional</option>
              <option value="pharmacy">Pharmacy</option>
            </select>
          </Field>
          <Field label="Claim ID" hint="optional — auto-generated if left blank">
            <input
              value={form.claim_id}
              onChange={(e) => update("claim_id", e.target.value)}
              placeholder="CLM-1008"
              className="input"
            />
          </Field>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="block text-xs font-medium text-slate-600">
              Documents <span className="text-red-500">*</span>
              <span className="ml-1 font-normal text-slate-400">(PDF, PNG, JPG, TIFF · max 20 MB each)</span>
            </label>
            <select
              value={form.doc_type}
              onChange={(e) => update("doc_type", e.target.value)}
              className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600"
            >
              {DOC_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            className={`flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-6 text-center ${
              dragging ? "border-blue-400 bg-blue-50" : "border-slate-300"
            }`}
          >
            <UploadCloud size={20} className="text-slate-400" />
            <span className="text-sm text-slate-500">Drag files here, or</span>
            <label className="cursor-pointer rounded-md bg-white px-3 py-1.5 text-sm font-medium text-blue-600 ring-1 ring-inset ring-blue-200 hover:bg-blue-50">
              Choose files
              <input
                type="file"
                multiple
                accept={ACCEPT}
                className="sr-only"
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
          </div>

          {files.length > 0 && (
            <ul className="mt-2 space-y-1">
              {files.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-1.5 text-xs text-slate-600"
                >
                  <span>
                    {f.name} <span className="text-slate-400">· {formatBytes(f.size)}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                    className="text-slate-400 hover:text-red-500"
                  >
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{error}</p>
        )}

        {rejected.length > 0 && <RejectedList rejected={rejected} />}

        <button
          type="submit"
          disabled={submitting || files.length === 0}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Uploading {files.length} document{files.length > 1 ? "s" : ""}...
            </>
          ) : files.length === 0 ? (
            "Attach documents to continue"
          ) : (
            `Upload ${files.length} document${files.length > 1 ? "s" : ""} & create claim`
          )}
        </button>
      </form>
    </div>
  );
}

/** What was stored: the claim record, and one record per accepted file. */
function UploadSummary({ result, onOpen }: { result: IntakeResult; onOpen: () => void }) {
  const { claim, accepted, rejected } = result;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="card p-6">
        <div className="flex items-center gap-2 text-emerald-700">
          <CheckCircle2 size={18} />
          <h1 className="text-lg font-semibold">Claim {claim.claim_id} created</h1>
        </div>
        <dl className="mt-3 grid grid-cols-4 gap-4 text-sm">
          <Info label="Claim ID" value={claim.claim_id} />
          <Info label="Status" value={claim.status} />
          <Info label="Patient" value={claim.patient_id} />
          <Info label="Payer" value={claim.payer_name} />
        </dl>
      </div>

      <div className="card p-6">
        <h2 className="mb-3 text-sm font-semibold text-slate-800">
          {accepted.length} document{accepted.length === 1 ? "" : "s"} stored
        </h2>
        <ul className="space-y-3">
          {accepted.map((d) => (
            <li key={d.doc_id} className="rounded-lg border border-slate-100 p-3 text-sm">
              <div className="flex items-center gap-2 font-medium text-slate-800">
                <FileText size={15} className="text-slate-400" />
                {d.original_filename}
              </div>
              <dl className="mt-2 grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
                <Info label="Document ID" value={d.doc_id} />
                <Info label="Type" value={`${d.doc_type.replace(/_/g, " ")} · ${d.detected_type.toUpperCase()}`} />
                <Info label="Pages · Size" value={`${d.page_count ?? "?"} · ${formatBytes(d.size_bytes)}`} />
                <div className="col-span-3">
                  <Info label="Stored at" value={d.source_uri} mono />
                </div>
                <div className="col-span-3">
                  <Info label="SHA-256 fingerprint" value={d.sha256} mono />
                </div>
              </dl>
              {d.warnings?.length > 0 && <div className="mt-2 text-xs text-amber-600">{d.warnings.join(", ")}</div>}
            </li>
          ))}
        </ul>
      </div>

      {rejected.length > 0 && <RejectedList rejected={rejected} />}

      <button
        onClick={onOpen}
        className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
      >
        Open claim {claim.claim_id}
      </button>
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 break-all text-slate-800 ${mono ? "font-mono text-xs" : "font-medium"}`}>{value}</dd>
    </div>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-slate-600">
        {label} {required && <span className="text-red-500">*</span>}
        {hint && <span className="ml-1 font-normal text-slate-400">({hint})</span>}
      </label>
      {children}
    </div>
  );
}
