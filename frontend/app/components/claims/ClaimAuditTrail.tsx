"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, CheckCircle, FileText, Upload, User, AlertCircle, RefreshCw } from "lucide-react";
import Button from "../ui/Button";
import Alert from "../ui/Alert";
import LoadingSpinner from "../ui/LoadingSpinner";
import EmptyState from "../ui/EmptyState";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type AuditEntry = {
  _id: string;
  ledger_id: string;
  claim_id: string;
  sequence_number: number;
  timestamp: string;
  record_hash: string;
  prev_hash: string;
  event_type?: string;
  adjudication_id?: string;
  ref_id?: string;
};

interface ClaimAuditTrailProps {
  claimId: string;
}

export default function ClaimAuditTrail({ claimId }: ClaimAuditTrailProps) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<{ valid: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAuditEntries();
  }, [claimId]);

  const loadAuditEntries = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/audit/entries/${claimId}`);
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const data = await response.json();
      setEntries(data.entries || []);
    } catch (err: any) {
      setError(err.message || "Failed to load audit entries");
    } finally {
      setLoading(false);
    }
  };

  const verifyChain = async () => {
    setVerifying(true);
    setVerificationResult(null);
    try {
      const response = await fetch(`${API_BASE_URL}/audit/verify/${claimId}`);
      const data = await response.json();
      setVerificationResult({
        valid: data.chain_valid,
        message: data.message,
      });
    } catch (err: any) {
      setVerificationResult({
        valid: false,
        message: `Verification failed: ${err.message}`,
      });
    } finally {
      setVerifying(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getEventIcon = (eventType?: string) => {
    switch (eventType) {
      case "CLAIM_CREATED":
        return <FileText size={16} className="text-blue-600" />;
      case "DOCUMENT_UPLOADED":
        return <Upload size={16} className="text-purple-600" />;
      case "REVIEWER_DECISION":
        return <User size={16} className="text-emerald-600" />;
      case "OCR_COMPLETED":
        return <FileText size={16} className="text-indigo-600" />;
      default:
        return <ShieldCheck size={16} className="text-slate-600" />;
    }
  };

  const getEventColor = (eventType?: string) => {
    switch (eventType) {
      case "CLAIM_CREATED":
        return "bg-blue-50 border-blue-200 text-blue-700";
      case "DOCUMENT_UPLOADED":
        return "bg-purple-50 border-purple-200 text-purple-700";
      case "REVIEWER_DECISION":
        return "bg-emerald-50 border-emerald-200 text-emerald-700";
      case "OCR_COMPLETED":
        return "bg-indigo-50 border-indigo-200 text-indigo-700";
      default:
        return "bg-slate-50 border-slate-200 text-slate-700";
    }
  };

  const getEventLabel = (eventType?: string) => {
    switch (eventType) {
      case "CLAIM_CREATED":
        return "Claim Created";
      case "DOCUMENT_UPLOADED":
        return "Document Uploaded";
      case "REVIEWER_DECISION":
        return "Reviewer Decision";
      case "OCR_COMPLETED":
        return "OCR Completed";
      default:
        return "Adjudication";
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Audit Trail</h2>
            <p className="text-xs text-slate-500 mt-1">
              Hash-chained tamper-evident ledger for Claim {claimId}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={loadAuditEntries} variant="outline" size="sm" disabled={loading}>
              <RefreshCw size={14} />
              Refresh
            </Button>
            <Button onClick={verifyChain} variant="primary" size="sm" disabled={verifying || entries.length === 0}>
              <CheckCircle size={14} />
              {verifying ? "Verifying..." : "Verify Chain"}
            </Button>
          </div>
        </div>

        {/* Verification Result */}
        {verificationResult && (
          <Alert type={verificationResult.valid ? "success" : "error"} title="Chain Verification">
            {verificationResult.message}
          </Alert>
        )}

        {/* Info */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-700">
          <strong>How it works:</strong> Each entry's hash = SHA256(payload + previous hash). Any
          modification to past entries breaks the entire chain.
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert type="error" title="Failed to load audit trail">
          {error}
        </Alert>
      )}

      {/* Loading */}
      {loading && <LoadingSpinner message="Loading audit entries..." />}

      {/* Empty State */}
      {!loading && !error && entries.length === 0 && (
        <EmptyState
          icon={<ShieldCheck size={48} />}
          title="No audit entries yet"
          description="Audit entries will appear here as events occur for this claim."
        />
      )}

      {/* Audit Entries */}
      {!loading && entries.length > 0 && (
        <div className="space-y-3">
          {entries.map((entry, idx) => (
            <div
              key={entry._id}
              className={`border rounded-lg p-4 transition-all ${getEventColor(entry.event_type)}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  {getEventIcon(entry.event_type)}
                  <span className="font-semibold text-sm">{getEventLabel(entry.event_type)}</span>
                  <span className="text-xs px-2 py-0.5 bg-white/50 rounded font-mono">
                    Sequence #{entry.sequence_number}
                  </span>
                </div>
                <div className="text-xs text-slate-600">{formatTimestamp(entry.timestamp)}</div>
              </div>

              {/* Entry Details */}
              <div className="grid grid-cols-2 gap-3 text-xs mb-3">
                {entry.adjudication_id && (
                  <div>
                    <span className="text-slate-600">Adjudication ID:</span>
                    <div className="font-mono font-semibold">{entry.adjudication_id}</div>
                  </div>
                )}
                {entry.ref_id && (
                  <div>
                    <span className="text-slate-600">Reference ID:</span>
                    <div className="font-mono font-semibold">{entry.ref_id}</div>
                  </div>
                )}
              </div>

              {/* Hash Details */}
              <details className="text-xs">
                <summary className="cursor-pointer text-slate-600 hover:text-slate-800 font-medium mb-2">
                  View Hash Details
                </summary>
                <div className="space-y-2 bg-white/50 p-3 rounded border border-slate-200">
                  <div>
                    <span className="text-slate-600 font-medium">Ledger ID:</span>
                    <div className="font-mono text-[10px] mt-0.5">{entry.ledger_id}</div>
                  </div>
                  <div>
                    <span className="text-slate-600 font-medium">Record Hash:</span>
                    <div className="font-mono text-[10px] mt-0.5 break-all text-slate-700">
                      {entry.record_hash}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-600 font-medium">Previous Hash:</span>
                    <div className="font-mono text-[10px] mt-0.5 break-all text-slate-700">
                      {entry.prev_hash}
                    </div>
                  </div>
                  {entry.prev_hash === "GENESIS" && (
                    <div className="text-xs text-slate-500 italic mt-2">
                      ⚡ This is the first entry in the chain (Genesis)
                    </div>
                  )}
                </div>
              </details>
            </div>
          ))}
        </div>
      )}

      {/* Summary */}
      {entries.length > 0 && (
        <div className="card p-4 bg-slate-50">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-slate-600" />
              <span className="font-medium text-slate-700">Total Entries:</span>
              <span className="font-bold text-slate-900">{entries.length}</span>
            </div>
            <div className="text-xs text-slate-500">
              Chain from #{entries[entries.length - 1]?.sequence_number} to #{entries[0]?.sequence_number}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
