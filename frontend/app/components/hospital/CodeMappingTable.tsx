"use client";

import { Check, AlertCircle, Edit2 } from "lucide-react";
import Badge from "../ui/Badge";

interface CodeMapping {
  id: string;
  hospitalTerm: string;
  standardType: "ICD-10" | "CPT" | "RxNorm" | "HCPCS";
  code: string;
  description: string;
  confidence: number;
  status: "auto-mapped" | "needs-review" | "manually-confirmed";
  alternatives?: {
    code: string;
    description: string;
    score: number;
  }[];
}

interface CodeMappingTableProps {
  mappings: CodeMapping[];
  onSelectMapping?: (id: string, code: string) => void;
  onConfirm?: (id: string) => void;
}

export default function CodeMappingTable({ mappings, onSelectMapping, onConfirm }: CodeMappingTableProps) {
  return (
    <div className="space-y-4">
      {mappings.map((mapping) => (
        <div
          key={mapping.id}
          className={`card overflow-hidden ${
            mapping.status === "needs-review" ? "ring-2 ring-amber-500/50" : ""
          }`}
        >
          <div className="flex items-start justify-between p-4">
            {/* Left: Hospital Term */}
            <div className="flex-1">
              <div className="text-xs font-medium text-slate-500 mb-1">Hospital Terminology</div>
              <div className="text-base font-semibold text-slate-900">{mapping.hospitalTerm}</div>
            </div>

            {/* Arrow */}
            <div className="px-4 py-2">
              <div className="text-slate-400">→</div>
            </div>

            {/* Right: Standardized Code */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <div className="text-xs font-medium text-slate-500">{mapping.standardType}</div>
                <ConfidenceBadge confidence={mapping.confidence} />
                <StatusBadge status={mapping.status} />
              </div>
              <div className="flex items-center gap-2">
                <div className="text-base font-semibold text-slate-900">
                  {mapping.code}
                </div>
                {mapping.status === "manually-confirmed" && (
                  <Check size={16} className="text-emerald-600" />
                )}
              </div>
              <div className="text-sm text-slate-600 mt-0.5">{mapping.description}</div>
            </div>

            {/* Actions */}
            {mapping.status !== "manually-confirmed" && (
              <div className="ml-4">
                {mapping.status === "auto-mapped" && onConfirm && (
                  <button
                    onClick={() => onConfirm(mapping.id)}
                    className="flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700"
                  >
                    <Check size={14} />
                    Confirm
                  </button>
                )}
                {mapping.status === "needs-review" && (
                  <div className="flex items-center gap-1 text-amber-600">
                    <AlertCircle size={16} />
                    <span className="text-sm font-medium">Review Required</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Alternatives for review */}
          {mapping.status === "needs-review" && mapping.alternatives && (
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-700 mb-2">Possible matches:</div>
              <div className="space-y-2">
                {mapping.alternatives.map((alt, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelectMapping?.(mapping.id, alt.code)}
                    className="flex items-start gap-2 w-full text-left p-2 rounded border border-slate-200 hover:border-blue-300 hover:bg-white transition-colors"
                  >
                    <input type="radio" name={`mapping-${mapping.id}`} className="mt-0.5" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-slate-800">
                        {alt.code} — {alt.description}
                      </div>
                      <div className="text-xs text-slate-500">Match score: {Math.round(alt.score * 100)}%</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percentage = Math.round(confidence * 100);
  const variant = confidence >= 0.9 ? "success" : confidence >= 0.7 ? "warning" : "error";

  return (
    <Badge variant={variant}>
      {percentage}% confidence
    </Badge>
  );
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "auto-mapped":
      return <Badge variant="info">Auto-mapped</Badge>;
    case "needs-review":
      return <Badge variant="warning">Needs review</Badge>;
    case "manually-confirmed":
      return <Badge variant="success">Confirmed</Badge>;
    default:
      return <Badge variant="neutral">{status}</Badge>;
  }
}
