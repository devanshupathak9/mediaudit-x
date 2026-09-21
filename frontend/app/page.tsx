/**
 * Home dashboard — real data from GET /claims (no fabricated trend
 * numbers/deltas: this project's whole thesis is "don't show a number
 * you can't back up", so unlike a typical mockup dashboard this only
 * shows counts actually computed from what's in Elasticsearch right now).
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileStack, Clock, XCircle, CheckCircle2, Upload, Search, ShieldCheck, ClipboardList } from "lucide-react";
import StatCard from "./components/StatCard";
import StatusBadge from "./components/StatusBadge";
import DonutChart from "./components/DonutChart";
import LoadingSpinner from "./components/ui/LoadingSpinner";
import { useRole } from "./contexts/RoleContext";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type Claim = {
  id: string;
  claim_id: string;
  patient_id: string;
  cpt_code: string;
  claim_amount: number;
  status: string;
  ai_recommendation?: { status: string };
};

export default function HomePage() {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const { role, userName } = useRole();

  useEffect(() => {
    fetch(`${API_BASE_URL}/claims?limit=200`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setClaims(data);
        setFetchError(null);
        setLoading(false);
      })
      .catch((err) => {
        // Distinguish "backend unreachable / CORS / 5xx" from "the
        // index is genuinely empty" -- these previously looked
        // identical (both rendered the empty "No claims found" state),
        // which made a network/CORS failure indistinguishable from an
        // empty insurance-claims index.
        setFetchError(
          `Could not load claims from ${API_BASE_URL} (${err.message}). Is the backend running, and does its CORS allow_origins include this page's exact origin (${typeof window !== "undefined" ? window.location.origin : "?"})?`
        );
        setLoading(false);
      });
  }, []);

  const total = claims.length;
  const pending = claims.filter((c) => c.status === "PENDING").length;
  const denied = claims.filter((c) => c.status === "DENIED").length;
  const approved = claims.filter((c) => c.status === "APPROVED").length;
  const draft = claims.filter((c) => c.status === "DRAFT").length;
  const submitted = claims.filter((c) => c.status === "SUBMITTED").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">
          {role === "hospital" ? `Welcome back, ${userName}` : `Welcome back, ${userName}`}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {role === "hospital"
            ? "Manage and track your insurance claims"
            : "Here's what's happening with your claims today"}
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {role === "hospital" ? (
          <>
            <StatCard icon={FileStack} iconBg="bg-blue-50" iconColor="text-blue-600" label="Draft Claims" value={loading ? "…" : draft} />
            <StatCard icon={Upload} iconBg="bg-purple-50" iconColor="text-purple-600" label="Submitted" value={loading ? "…" : submitted} />
            <StatCard icon={Clock} iconBg="bg-amber-50" iconColor="text-amber-600" label="In Review" value={loading ? "…" : pending} />
            <StatCard icon={CheckCircle2} iconBg="bg-emerald-50" iconColor="text-emerald-600" label="Approved" value={loading ? "…" : approved} />
          </>
        ) : (
          <>
            <StatCard icon={FileStack} iconBg="bg-blue-50" iconColor="text-blue-600" label="Total Claims" value={loading ? "…" : total} />
            <StatCard icon={Clock} iconBg="bg-amber-50" iconColor="text-amber-600" label="Pending Review" value={loading ? "…" : pending} />
            <StatCard icon={XCircle} iconBg="bg-red-50" iconColor="text-red-600" label="Denied Claims" value={loading ? "…" : denied} />
            <StatCard icon={CheckCircle2} iconBg="bg-emerald-50" iconColor="text-emerald-600" label="Approved Claims" value={loading ? "…" : approved} />
          </>
        )}
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="card col-span-2 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">Recent Claims</h2>
            <Link href="/claims" className="text-xs font-medium text-blue-600 hover:underline">
              View all
            </Link>
          </div>
          {loading ? (
            <LoadingSpinner size={20} className="py-8" message="Loading claims..." />
          ) : fetchError ? (
            <p className="py-8 text-center text-sm text-red-500">{fetchError}</p>
          ) : claims.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">
              No claims found. Run <code className="rounded bg-slate-100 px-1">python -m app.ingestion.load_sample_data</code> to load sample fixtures.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="pb-2 font-medium">Claim ID</th>
                  <th className="pb-2 font-medium">Patient</th>
                  <th className="pb-2 font-medium">CPT</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Amount</th>
                  <th className="pb-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {claims.slice(0, 6).map((claim) => (
                  <tr key={claim.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2.5 font-medium text-slate-800">{claim.claim_id}</td>
                    <td className="py-2.5 text-slate-500">{claim.patient_id}</td>
                    <td className="py-2.5 text-slate-500">{claim.cpt_code}</td>
                    <td className="py-2.5">
                      <StatusBadge status={claim.status} aiRecommendation={claim.ai_recommendation?.status} />
                    </td>
                    <td className="py-2.5 text-slate-700">${claim.claim_amount?.toLocaleString()}</td>
                    <td className="py-2.5 text-right">
                      <Link
                        href={role === "hospital" ? `/hospital/claims/${claim.claim_id}` : `/insurance/review/${claim.claim_id}`}
                        className="text-xs font-medium text-blue-600 hover:underline"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="space-y-6">
          <div className="card p-5">
            <h2 className="mb-3 text-sm font-semibold text-slate-800">Claim Outcome Breakdown</h2>
            {loading || total === 0 ? (
              <p className="text-sm text-slate-400">No data yet.</p>
            ) : (
              <DonutChart
                centerLabel="Total Claims"
                centerValue={total}
                segments={[
                  { label: "Approved", value: approved, color: "#10b981" },
                  { label: "Denied", value: denied, color: "#ef4444" },
                  { label: "Pending", value: pending, color: "#f59e0b" },
                ]}
              />
            )}
          </div>

          <div className="card p-5">
            <h2 className="mb-3 text-sm font-semibold text-slate-800">Quick Actions</h2>
            <div className="space-y-2">
              {role === "hospital" ? (
                <>
                  <QuickAction icon={Upload} label="Create New Claim" href="/hospital/create-claim" />
                  <QuickAction icon={FileStack} label="View All Claims" href="/claims" />
                  <QuickAction icon={ShieldCheck} label="View Audit Trail" href="/audit-trail" />
                </>
              ) : (
                <>
                  <QuickAction icon={ClipboardList} label="Review Queue" href="/review-queue" />
                  <QuickAction icon={Search} label="Search Policy" href="/policy-lookup" />
                  <QuickAction icon={ShieldCheck} label="View Audit Trail" href="/audit-trail" />
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function QuickAction({
  icon: Icon,
  label,
  href,
  note,
}: {
  icon: any;
  label: string;
  href: string;
  note?: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2.5 text-sm text-slate-700 hover:border-blue-200 hover:bg-blue-50/50"
    >
      <span className="flex items-center gap-2">
        <Icon size={15} className="text-slate-400" />
        {label}
      </span>
      {note && <span className="text-xs text-slate-400">{note}</span>}
    </Link>
  );
}
