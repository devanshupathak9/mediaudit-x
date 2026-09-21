"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle, AlertCircle } from "lucide-react";
import CodeMappingTable from "../../../components/hospital/CodeMappingTable";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";

// Demo data for mapping
const DEMO_MAPPINGS = [
  {
    id: "1",
    hospitalTerm: "Type II Diabetes Mellitus",
    standardType: "ICD-10" as const,
    code: "E11.9",
    description: "Type 2 diabetes mellitus without complications",
    confidence: 0.98,
    status: "auto-mapped" as const,
  },
  {
    id: "2",
    hospitalTerm: "Total Knee Replacement",
    standardType: "CPT" as const,
    code: "27447",
    description: "Total knee arthroplasty",
    confidence: 0.96,
    status: "auto-mapped" as const,
  },
  {
    id: "3",
    hospitalTerm: "Metformin 500mg",
    standardType: "RxNorm" as const,
    code: "860975",
    description: "Metformin hydrochloride 500 MG Oral Tablet",
    confidence: 0.94,
    status: "auto-mapped" as const,
  },
  {
    id: "4",
    hospitalTerm: "Chronic knee degeneration",
    standardType: "ICD-10" as const,
    code: "M17.10",
    description: "Unilateral primary osteoarthritis, unspecified knee",
    confidence: 0.72,
    status: "needs-review" as const,
    alternatives: [
      { code: "M17.10", description: "Unilateral primary osteoarthritis, unspecified knee", score: 0.72 },
      { code: "M17.11", description: "Unilateral primary osteoarthritis, right knee", score: 0.68 },
      { code: "M17.12", description: "Unilateral primary osteoarthritis, left knee", score: 0.68 },
    ],
  },
];

export default function ClaimMappingPage() {
  const params = useParams();
  const router = useRouter();
  const claimId = params.id as string;

  const [mappings, setMappings] = useState(DEMO_MAPPINGS);
  const [saving, setSaving] = useState(false);

  const handleConfirm = (id: string) => {
    setMappings((prev) =>
      prev.map((m) => (m.id === id ? { ...m, status: "manually-confirmed" as const } : m))
    );
  };

  const handleSelectMapping = (id: string, code: string) => {
    setMappings((prev) =>
      prev.map((m) => {
        if (m.id === id) {
          const selected = m.alternatives?.find((a) => a.code === code);
          return selected
            ? { ...m, code: selected.code, description: selected.description, status: "manually-confirmed" as const }
            : m;
        }
        return m;
      })
    );
  };

  const handleSave = async () => {
    setSaving(true);
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setSaving(false);
    router.push(`/claims/${claimId}`);
  };

  const needsReview = mappings.filter((m) => m.status === "needs-review").length;
  const confirmed = mappings.filter((m) => m.status === "manually-confirmed").length;
  const autoMapped = mappings.filter((m) => m.status === "auto-mapped").length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <Link href={`/claims/${claimId}`} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-2">
          <ArrowLeft size={14} /> Back to Claim
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">Code Mapping & Normalization</h1>
        <p className="mt-1 text-sm text-slate-500">Review and confirm standardized medical codes for {claimId}</p>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-2xl font-semibold text-slate-900">{mappings.length}</div>
          <div className="text-xs text-slate-500">Total Codes</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-semibold text-emerald-600">{autoMapped + confirmed}</div>
          <div className="text-xs text-slate-500">Mapped</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-semibold text-amber-600">{needsReview}</div>
          <div className="text-xs text-slate-500">Needs Review</div>
        </div>
        <div className="card p-4">
          <div className="text-2xl font-semibold text-blue-600">{confirmed}</div>
          <div className="text-xs text-slate-500">Manually Confirmed</div>
        </div>
      </div>

      {/* Alerts */}
      {needsReview > 0 && (
        <Alert type="warning" title="Review Required">
          {needsReview} code mapping{needsReview > 1 ? "s" : ""} requires manual review. Please select the most appropriate match below.
        </Alert>
      )}

      {needsReview === 0 && (
        <Alert type="success" title="All Codes Mapped">
          All medical codes have been successfully mapped to standardized formats.
        </Alert>
      )}

      {/* Mapping Table */}
      <div>
        <h2 className="text-sm font-semibold text-slate-800 mb-3">Code Mappings</h2>
        <CodeMappingTable
          mappings={mappings}
          onSelectMapping={handleSelectMapping}
          onConfirm={handleConfirm}
        />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between card p-4">
        <div className="text-sm text-slate-600">
          {needsReview > 0 ? (
            <span className="flex items-center gap-2 text-amber-600">
              <AlertCircle size={16} />
              Please review all mappings before proceeding
            </span>
          ) : (
            <span className="flex items-center gap-2 text-emerald-600">
              <CheckCircle size={16} />
              All mappings confirmed
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push(`/claims/${claimId}`)}>
            Save as Draft
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            loading={saving}
            disabled={needsReview > 0}
          >
            Confirm & Continue
          </Button>
        </div>
      </div>
    </div>
  );
}
