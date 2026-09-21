"use client";

import Link from "next/link";
import { ShieldCheck, ArrowRight, FileText } from "lucide-react";

export default function AuditTrailPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Audit Trail</h1>
        <p className="mt-1 text-sm text-slate-500">
          Hash-chained tamper-evident ledger of all claim events
        </p>
      </div>

      {/* Info Card */}
      <div className="card p-8 text-center">
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center">
            <ShieldCheck size={32} className="text-blue-600" />
          </div>
        </div>

        <h2 className="text-xl font-semibold text-slate-900 mb-2">
          Audit Trail Moved to Claim Details
        </h2>

        <p className="text-sm text-slate-600 mb-6 max-w-2xl mx-auto">
          The audit trail is now integrated into each claim's detail page as a dedicated tab.
          This provides better context and allows you to see the complete audit history for
          each specific claim alongside other claim information.
        </p>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-6 text-left mb-6 max-w-xl mx-auto">
          <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <FileText size={16} className="text-blue-600" />
            How to view audit trail:
          </h3>
          <ol className="space-y-2 text-sm text-slate-700">
            <li className="flex items-start gap-2">
              <span className="font-semibold text-blue-600">1.</span>
              <span>Go to any claim from the claims list or review queue</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-semibold text-blue-600">2.</span>
              <span>Click the "Audit Trail" tab in the claim details</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-semibold text-blue-600">3.</span>
              <span>View all hash-chained entries for that specific claim</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-semibold text-blue-600">4.</span>
              <span>Verify chain integrity with one click</span>
            </li>
          </ol>
        </div>

        <div className="flex gap-3 justify-center">
          <Link
            href="/claims"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Go to Claims
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/review-queue"
            className="inline-flex items-center gap-2 rounded-lg border-2 border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Review Queue
            <ArrowRight size={16} />
          </Link>
        </div>
      </div>

      {/* Technical Info */}
      <div className="card p-6">
        <h3 className="text-sm font-semibold text-slate-900 mb-3">What's in the Audit Trail?</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="font-semibold text-blue-900 mb-1">📄 Claim Created</div>
            <div className="text-xs text-blue-700">Initial claim submission</div>
          </div>
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
            <div className="font-semibold text-purple-900 mb-1">📤 Document Uploaded</div>
            <div className="text-xs text-purple-700">Supporting documents added</div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
            <div className="font-semibold text-slate-900 mb-1">🛡️ Adjudication</div>
            <div className="text-xs text-slate-700">AI analysis completed</div>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
            <div className="font-semibold text-emerald-900 mb-1">👤 Reviewer Decision</div>
            <div className="text-xs text-emerald-700">Manual approval/denial recorded</div>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-slate-200">
          <p className="text-xs text-slate-600">
            <strong>Tamper-evident:</strong> Each entry's hash = SHA256(payload + previous hash).
            Any modification to past entries breaks the entire chain, making tampering immediately detectable.
          </p>
        </div>
      </div>
    </div>
  );
}
