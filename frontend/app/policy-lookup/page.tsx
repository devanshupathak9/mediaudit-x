"use client";
import { BookOpenCheck } from "lucide-react";
import ComingSoon from "../components/ComingSoon";

export default function PolicyLookupPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-900">Policy Lookup</h1>
      <p className="text-sm text-slate-500">
        The real hybrid (BM25 + RRF) policy search this would use already exists as a backend tool
        (<code className="rounded bg-slate-100 px-1">match_payer_coverage_policy</code>) and runs during
        adjudication — a standalone search UI over it isn't built yet.
      </p>
      <ComingSoon
        icon={BookOpenCheck}
        title="Direct Policy Search"
        description="Search medical-policies directly by payer, CPT/ICD code, or clinical indication, without going through a claim."
      />
    </div>
  );
}
