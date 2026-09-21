"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Filter, Search, CheckCircle2, AlertCircle, Clock, XCircle } from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import Badge from "../components/ui/Badge";
import Alert from "../components/ui/Alert";
import EmptyState from "../components/ui/EmptyState";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import { DemoDataManager } from "../lib/completeDemoData";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const USE_DEMO_DATA = false; // wired to the real backend API

type Claim = {
  id?: string;
  claim_id: string;
  patient_id: string;
  patient_name?: string;
  payer_name: string;
  cpt_code: string;
  icd10_code: string;
  claim_amount: number;
  status: string;
  submitted_date?: string;
  ai_recommendation?: "APPROVE" | "DENY" | "NEEDS_REVIEW" | "REQUEST_INFO";
  hospital?: string;
  procedure_name?: string;
};

const STATUS_FILTERS = ["All", "PENDING", "APPROVED", "DENIED", "REQUEST_INFO"] as const;
const AI_FILTERS = ["All AI Recommendations", "Approve Recommended", "Deny Recommended", "Needs Review"] as const;

export default function ReviewQueuePage() {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("All");
  const [aiFilter, setAiFilter] = useState<(typeof AI_FILTERS)[number]>("All AI Recommendations");
  const [searchQuery, setSearchQuery] = useState("");
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    if (USE_DEMO_DATA) {
      // Use demo data from localStorage
      const demoClaims = DemoDataManager.getAllClaims();

      // Show all claims (including approved and denied)
      setClaims(demoClaims as any[]);
      setLoading(false);
    } else {
      // Use real API. A failed request previously fell back to
      // DemoDataManager's localStorage fixtures silently, which could
      // make a broken backend/CORS connection look like a working (but
      // empty or fake) review queue. Surface the real error instead.
      fetch(`${API_BASE_URL}/claims?limit=200`)
        .then((res) => {
          if (!res.ok) throw new Error(`API returned ${res.status}`);
          return res.json();
        })
        .then((data) => {
          // Show all claims (including approved and denied)
          setClaims(data);
          setFetchError(null);
          setLoading(false);
        })
        .catch((err) => {
          setFetchError(
            `Could not load claims from ${API_BASE_URL} (${err.message}). Is the backend running, and does its CORS allow_origins include this page's exact origin (${typeof window !== "undefined" ? window.location.origin : "?"})?`
          );
          setLoading(false);
        });
    }
  }, []);

  const filtered = claims.filter((claim) => {
    // Status filter
    if (statusFilter !== "All" && claim.status !== statusFilter) return false;

    // AI recommendation filter
    if (aiFilter !== "All AI Recommendations") {
      if (aiFilter === "Approve Recommended" && claim.ai_recommendation !== "APPROVE") return false;
      if (aiFilter === "Deny Recommended" && claim.ai_recommendation !== "DENY") return false;
      if (aiFilter === "Needs Review" && claim.ai_recommendation !== "NEEDS_REVIEW") return false;
    }

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        claim.claim_id.toLowerCase().includes(query) ||
        claim.patient_id.toLowerCase().includes(query) ||
        claim.payer_name.toLowerCase().includes(query)
      );
    }

    return true;
  });

  const needsReview = claims.filter((c) => c.status === "PENDING").length;
  const needsInfo = claims.filter((c) => c.status === "REQUEST_INFO").length;
  const approved = claims.filter((c) => c.status === "APPROVED").length;
  const denied = claims.filter((c) => c.status === "DENIED").length;
  const approveRecommended = claims.filter((c) => c.ai_recommendation === "APPROVE").length;
  const needsHumanReview = claims.filter((c) => c.ai_recommendation === "NEEDS_REVIEW").length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Claims Review Queue</h1>
        <p className="mt-1 text-sm text-slate-500">Review and adjudicate incoming claims</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          icon={<Clock size={18} className="text-amber-600" />}
          label="Pending Review"
          value={needsReview}
          bgColor="bg-amber-50"
        />
        <StatCard
          icon={<CheckCircle2 size={18} className="text-emerald-600" />}
          label="Approved"
          value={approved}
          bgColor="bg-emerald-50"
        />
        <StatCard
          icon={<XCircle size={18} className="text-red-600" />}
          label="Denied"
          value={denied}
          bgColor="bg-red-50"
        />
      </div>

      {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[250px]">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search by Claim ID, Patient, or Payer..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input pl-9 w-full"
              />
            </div>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-slate-400" />
            <span className="text-sm font-medium text-slate-600">Status:</span>
            {STATUS_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  statusFilter === f
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* AI Filter */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-600">AI:</span>
            <select
              value={aiFilter}
              onChange={(e) => setAiFilter(e.target.value as typeof aiFilter)}
              className="input text-sm"
            >
              {AI_FILTERS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {fetchError && (
        <Alert type="error" title="Could not load claims">
          {fetchError}
        </Alert>
      )}

      {/* Claims Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <LoadingSpinner message="Loading review queue..." />
        ) : fetchError ? (
          <EmptyState
            icon={<AlertCircle size={48} />}
            title="Unable to load claims"
            description="Check the error message above for details."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<CheckCircle2 size={48} />}
            title="No claims match your filters"
            description="Try adjusting your filters or search query."
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3 font-medium">Claim ID</th>
                <th className="px-4 py-3 font-medium">Patient</th>
                <th className="px-4 py-3 font-medium">Payer</th>
                <th className="px-4 py-3 font-medium">Procedure</th>
                <th className="px-4 py-3 font-medium">Amount</th>
                <th className="px-4 py-3 font-medium">AI Recommendation</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Submitted</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((claim, idx) => (
                <tr key={claim.id || claim.claim_id || idx} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-medium text-slate-800">{claim.claim_id}</td>
                  <td className="px-4 py-3 text-slate-500">{claim.patient_name || claim.patient_id}</td>
                  <td className="px-4 py-3 text-slate-500">{claim.payer_name}</td>
                  <td className="px-4 py-3 text-slate-500">{claim.procedure_name || claim.cpt_code}</td>
                  <td className="px-4 py-3 text-slate-700">${claim.claim_amount?.toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <AIRecommendationBadge recommendation={claim.ai_recommendation?.status || claim.ai_recommendation} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={claim.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {claim.submitted_date || "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/insurance/review/${claim.claim_id}`}
                      className="text-xs font-medium text-blue-600 hover:underline"
                    >
                      Review
                    </Link>
                  </td>                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Results count */}
      <p className="text-sm text-slate-500 text-center">
        Showing {filtered.length} of {claims.length} claims in review queue
      </p>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  bgColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  bgColor: string;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${bgColor}`}>
          {icon}
        </div>
        <div>
          <div className="text-2xl font-semibold text-slate-900">{value}</div>
          <div className="text-xs text-slate-500">{label}</div>
        </div>
      </div>
    </div>
  );
}

function AIRecommendationBadge({ recommendation }: { recommendation?: string }) {
  if (!recommendation) {
    return <Badge variant="neutral">Not analyzed</Badge>;
  }

  switch (recommendation) {
    case "APPROVE":
      return (
        <Badge variant="success" dot>
          Approve recommended
        </Badge>
      );
    case "DENY":
      return (
        <Badge variant="error" dot>
          Deny recommended
        </Badge>
      );
    case "NEEDS_REVIEW":
      return (
        <Badge variant="warning" dot>
          Human review required
        </Badge>
      );
    case "REQUEST_INFO":
      return (
        <Badge variant="info" dot>
          Request information
        </Badge>
      );
    default:
      return <Badge variant="neutral">{recommendation}</Badge>;
  }
}
