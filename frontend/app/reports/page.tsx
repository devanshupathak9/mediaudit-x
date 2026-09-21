"use client";
import { BarChart3 } from "lucide-react";
import ComingSoon from "../components/ComingSoon";

export default function ReportsPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-900">Reports</h1>
      <p className="text-sm text-slate-500">
        Benchmark numbers here should come from <code className="rounded bg-slate-100 px-1">eval/run_benchmark.py</code> —
        that script is still a skeleton (Step 9 in the build spec). Wire it up and write its output to
        <code className="rounded bg-slate-100 px-1">benchmark_results.json</code> before pulling real numbers into this page.
      </p>
      <ComingSoon
        icon={BarChart3}
        title="Benchmark & Outcomes Dashboard"
        description="Policy recall@5, trajectory accuracy, hallucination spot-check, and p95 latency — sourced from a committed benchmark script, not invented."
      />
    </div>
  );
}
