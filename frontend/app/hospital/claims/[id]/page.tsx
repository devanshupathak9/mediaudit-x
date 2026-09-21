"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, FileText, Calendar, User, Building2, DollarSign, CheckCircle, Clock } from "lucide-react";
import StatusBadge from "../../../components/StatusBadge";
import LoadingSpinner from "../../../components/ui/LoadingSpinner";
import DocumentsPanel from "../../../components/DocumentsPanel";

type Review = {
  decision?: string;
  status: string;
  comment: string;
  reviewer_name?: string;
  decided_at?: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function HospitalClaimViewPage() {
  const params = useParams();
  const router = useRouter();
  const claimId = params.id as string;

  const [claim, setClaim] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  // Decisions made before the claim record stored latest_review only exist
  // in adjudication-results; this fallback reads the newest one from there.
  const [legacyReview, setLegacyReview] = useState<Review | null>(null);

  useEffect(() => {
    // Fetch claim details from API
    fetch(`${API_BASE_URL}/claims/${claimId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setClaim(data);
        setLoading(false);
        if (!data.latest_review) {
          fetch(`${API_BASE_URL}/claims/${claimId}/adjudications`)
            .then((res) => (res.ok ? res.json() : null))
            .then((adj) => {
              if (adj?.decision_type === "HUMAN_REVIEW" && adj.reviewer_comment) {
                setLegacyReview({
                  status: adj.status,
                  comment: adj.reviewer_comment,
                  reviewer_name: adj.decided_by,
                  decided_at: adj.decided_at,
                });
              }
            })
            .catch(() => {});
        }
      })
      .catch((error) => {
        console.error("Error fetching claim:", error);
        setFetchError(error?.message || "Could not reach the API");
        setLoading(false);
      });
  }, [claimId]);

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <LoadingSpinner size={32} message="Loading claim details..." />
      </div>
    );
  }

  if (!claim) {
    return (
      <div className="card p-8 text-center">
        <p className="text-slate-600">{fetchError ? `Could not load this claim: ${fetchError}` : "Claim not found"}</p>
        <Link href="/claims" className="text-blue-600 hover:underline mt-2 inline-block">
          Back to My Claims
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <Link href="/claims" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-2">
          <ArrowLeft size={14} /> Back to My Claims
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Claim Details</h1>
            <p className="text-sm text-slate-500 mt-1">Claim ID: {claim.claim_id}</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={claim.status} />
          </div>
        </div>
      </div>

      <InsuranceDecision
        latest={claim.latest_review || legacyReview}
        history={claim.review_history || []}
      />

      {claim.status === "REQUEST_INFO" && (
        <DocumentsPanel
          claimId={claim.claim_id}
          claimStatus={claim.status}
          apiBaseUrl={API_BASE_URL}
          onClaimChanged={(updated) => updated && setClaim((prev: any) => ({ ...prev, ...updated }))}
        />
      )}

      {/* Read-Only Notice */}
      <div className="card border-2 border-blue-200 bg-blue-50 p-4">
        <div className="flex items-start gap-3">
          <FileText size={20} className="text-blue-600 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-blue-900 text-sm">Claim Submitted</h3>
            <p className="text-sm text-blue-700 mt-1">
              This claim has been submitted to the insurance company. You can view all details below, but modifications are no longer allowed.
            </p>
          </div>
        </div>
      </div>

      {/* Patient Information */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <User size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Patient Information</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Patient Name:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.patient_name || claim.patient_id}</div>
          </div>
          <div>
            <span className="text-slate-500">Patient ID:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.patient_id}</div>
          </div>
          {claim.patient_age && (
            <div>
              <span className="text-slate-500">Age:</span>
              <div className="font-semibold text-slate-900 mt-1">{claim.patient_age}</div>
            </div>
          )}
          {claim.patient_gender && (
            <div>
              <span className="text-slate-500">Gender:</span>
              <div className="font-semibold text-slate-900 mt-1">{claim.patient_gender}</div>
            </div>
          )}
        </div>
      </div>

      {/* Admission Details */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Calendar size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Admission Details</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Admission Date:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.admission_date || "—"}</div>
          </div>
          <div>
            <span className="text-slate-500">Discharge Date:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.discharge_date || "—"}</div>
          </div>
          <div>
            <span className="text-slate-500">Department:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.department || "—"}</div>
          </div>
          <div>
            <span className="text-slate-500">Attending Physician:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.attending_physician || "—"}</div>
          </div>
        </div>
      </div>

      {/* Clinical Information */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <FileText size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Clinical Information</h2>
        </div>
        <div className="space-y-4 text-sm">
          <div>
            <span className="text-slate-500">Diagnosis:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.diagnosis_description || "—"}</div>
          </div>
          <div>
            <span className="text-slate-500">Procedure:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.procedure_name || "—"}</div>
          </div>
          {claim.icd10_code && (
            <div>
              <span className="text-slate-500">ICD-10 Code:</span>
              <div className="font-mono text-slate-900 mt-1">{claim.icd10_code}</div>
            </div>
          )}
          {claim.cpt_code && (
            <div>
              <span className="text-slate-500">CPT Code:</span>
              <div className="font-mono text-slate-900 mt-1">{claim.cpt_code}</div>
            </div>
          )}
        </div>
      </div>

      {/* Hospital & Insurance */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Building2 size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Hospital & Insurance</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Hospital:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.hospital || "—"}</div>
          </div>
          <div>
            <span className="text-slate-500">Insurance Provider:</span>
            <div className="font-semibold text-slate-900 mt-1">{claim.payer_name || "—"}</div>
          </div>
          {claim.policy_id && (
            <div>
              <span className="text-slate-500">Policy ID:</span>
              <div className="font-semibold text-slate-900 mt-1">{claim.policy_id}</div>
            </div>
          )}
        </div>
      </div>

      {/* Billing Information */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <DollarSign size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Billing Information</h2>
        </div>
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Total Claim Amount:</span>
            <span className="text-2xl font-bold text-slate-900">
              ${claim.claim_amount?.toLocaleString() || "0"}
            </span>
          </div>
        </div>
      </div>

      {/* Status Timeline */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Clock size={20} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-900">Claim Status</h2>
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${claim.status === "DRAFT" ? "bg-slate-400" : "bg-green-500"}`}></div>
            <div className="flex-1">
              <div className="font-medium text-slate-900 text-sm">Submitted</div>
              <div className="text-xs text-slate-500">{claim.submitted_date || "Pending"}</div>
            </div>
            {claim.status !== "DRAFT" && <CheckCircle size={18} className="text-green-500" />}
          </div>

          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${
              claim.status === "APPROVED" || claim.status === "DENIED" ? "bg-green-500" : "bg-slate-300"
            }`}></div>
            <div className="flex-1">
              <div className="font-medium text-slate-900 text-sm">Reviewed by Insurance</div>
              <div className="text-xs text-slate-500">
                {claim.status === "APPROVED" || claim.status === "DENIED" ? "Completed" : "Pending"}
              </div>
            </div>
            {(claim.status === "APPROVED" || claim.status === "DENIED") && (
              <CheckCircle size={18} className="text-green-500" />
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${claim.status === "APPROVED" ? "bg-green-500" : "bg-slate-300"}`}></div>
            <div className="flex-1">
              <div className="font-medium text-slate-900 text-sm">Approved</div>
              <div className="text-xs text-slate-500">
                {claim.status === "APPROVED" ? "Claim approved" : "Pending approval"}
              </div>
            </div>
            {claim.status === "APPROVED" && <CheckCircle size={18} className="text-green-500" />}
          </div>
        </div>
      </div>

      {/* Footer Note */}
      <div className="text-center text-sm text-slate-500 pb-6">
        <p>If you have questions about this claim, please contact your insurance provider.</p>
      </div>
    </div>
  );
}

const DECISION_STYLES: Record<string, { box: string; title: string; label: string }> = {
  APPROVED: { box: "border-emerald-200 bg-emerald-50", title: "text-emerald-900", label: "Approved by insurance" },
  DENIED: { box: "border-red-200 bg-red-50", title: "text-red-900", label: "Denied by insurance" },
  REQUEST_INFO: {
    box: "border-amber-200 bg-amber-50",
    title: "text-amber-900",
    label: "Insurance requested more information",
  },
};

/** The insurance reviewer's decision and comment, newest first. */
function InsuranceDecision({ latest, history }: { latest: Review | null; history: Review[] }) {
  if (!latest) return null;
  const style = DECISION_STYLES[latest.status] || {
    box: "border-slate-200 bg-slate-50",
    title: "text-slate-900",
    label: `Insurance decision: ${latest.status}`,
  };
  const earlier = history.filter((r) => r.decided_at !== latest.decided_at).reverse();

  return (
    <div className={`card border-2 p-5 ${style.box}`}>
      <div className="flex items-center justify-between">
        <h2 className={`text-lg font-semibold ${style.title}`}>{style.label}</h2>
        <StatusBadge status={latest.status} />
      </div>
      <div className="mt-3 rounded-lg bg-white/70 p-3 text-sm text-slate-800 whitespace-pre-wrap">{latest.comment}</div>
      <div className="mt-2 text-xs text-slate-500">
        {latest.reviewer_name || "Insurance reviewer"}
        {latest.decided_at && ` · ${new Date(latest.decided_at).toLocaleString()}`}
      </div>
      {latest.status === "REQUEST_INFO" && (
        <p className="mt-3 text-sm text-amber-800">
          Upload the requested documents below; the claim goes back for review once they are added.
        </p>
      )}
      {earlier.length > 0 && (
        <div className="mt-4 border-t border-black/5 pt-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Earlier decisions</div>
          <ul className="space-y-2">
            {earlier.map((r, i) => (
              <li key={i} className="text-sm text-slate-700">
                <span className="font-medium">{r.status}</span> — {r.comment}
                <span className="text-xs text-slate-500">
                  {" "}
                  · {r.reviewer_name || "Insurance reviewer"}
                  {r.decided_at && `, ${new Date(r.decided_at).toLocaleString()}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
