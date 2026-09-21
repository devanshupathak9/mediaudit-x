"use client";

import { useState } from "react";
import { CheckCircle, XCircle, AlertCircle } from "lucide-react";
import Button from "../ui/Button";
import Modal from "../ui/Modal";
import Alert from "../ui/Alert";

interface ReviewerDecisionPanelProps {
  claimId: string;
  aiRecommendation?: string;
  currentStatus?: string;
  reviewerComment?: string;
  onDecisionSubmit?: (decision: "APPROVED" | "DENIED" | "REQUEST_INFO", comment: string) => void | Promise<void>;
}

export default function ReviewerDecisionPanel({
  claimId,
  aiRecommendation,
  currentStatus,
  reviewerComment,
  onDecisionSubmit,
}: ReviewerDecisionPanelProps) {
  const [selectedDecision, setSelectedDecision] = useState<"APPROVED" | "DENIED" | "REQUEST_INFO" | null>(null);
  const [comment, setComment] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Check if a final decision has been made
  const isDecisionMade = currentStatus === "APPROVED" || currentStatus === "DENIED";
  const finalDecision = isDecisionMade ? currentStatus : null;

  const handleSubmit = () => {
    if (!selectedDecision || !comment.trim()) return;
    setShowConfirm(true);
  };

  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleConfirm = async () => {
    if (!selectedDecision || !comment.trim()) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      await onDecisionSubmit?.(selectedDecision, comment);
      setShowConfirm(false);
    } catch (error: any) {
      console.error("Failed to submit decision", error);
      setSubmitError(error?.message || "Failed to submit decision. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // If decision is already made, show read-only summary
  if (isDecisionMade) {
    return (
      <div className="card p-6 border-2 border-slate-200">
        <div className="flex items-start gap-4">
          <div className={`flex-shrink-0 w-14 h-14 rounded-full flex items-center justify-center ${
            finalDecision === "APPROVED" ? "bg-emerald-100" : "bg-red-100"
          }`}>
            {finalDecision === "APPROVED" ? (
              <CheckCircle size={28} className="text-emerald-600" />
            ) : (
              <XCircle size={28} className="text-red-600" />
            )}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-lg font-semibold text-slate-900">
                {finalDecision === "APPROVED" ? "Claim Approved" : "Claim Denied"}
              </h2>
              <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                finalDecision === "APPROVED"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-red-100 text-red-700"
              }`}>
                {finalDecision}
              </span>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Final decision recorded. This claim has been {finalDecision === "APPROVED" ? "approved" : "denied"} by the reviewer.
            </p>

            {/* Decision Details Grid */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">AI Recommendation</div>
                <div className="text-sm font-semibold text-slate-800">
                  {aiRecommendation || "N/A"}
                </div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Final Decision</div>
                <div className={`text-sm font-semibold ${
                  finalDecision === "APPROVED" ? "text-emerald-700" : "text-red-700"
                }`}>
                  {finalDecision}
                </div>
              </div>
            </div>

            {/* Reviewer Comment */}
            {reviewerComment && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="text-xs font-medium text-blue-700 mb-2">Reviewer Comment:</div>
                <div className="text-sm text-slate-700 leading-relaxed">{reviewerComment}</div>
              </div>
            )}

            {/* Audit Trail Note */}
            <div className="mt-4 pt-4 border-t border-slate-200">
              <p className="text-xs text-slate-500">
                ✓ Decision recorded in audit trail • No further changes allowed
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-1">Final Reviewer Decision</h2>
        <p className="text-sm text-slate-600 mb-5">
          The AI recommendation is advisory. You are responsible for the final claim decision.
        </p>

        {/* AI Recommendation Display */}
        {aiRecommendation && (
          <div className="mb-5 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                <span className="text-blue-600 font-semibold text-sm">AI</span>
              </div>
              <div className="text-xs font-semibold text-blue-700">AI Recommendation</div>
            </div>
            <div className="text-sm font-semibold text-slate-800 ml-10">{aiRecommendation}</div>
          </div>
        )}

        {/* Decision Options */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-slate-700 mb-3">Your Decision *</label>
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => setSelectedDecision("APPROVED")}
              className={`flex items-center gap-2 p-4 rounded-lg border-2 transition-all ${
                selectedDecision === "APPROVED"
                  ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                  : "border-slate-200 hover:border-slate-300 text-slate-700"
              }`}
            >
              <CheckCircle size={20} />
              <span className="font-medium">Approve Claim</span>
            </button>

            <button
              onClick={() => setSelectedDecision("DENIED")}
              className={`flex items-center gap-2 p-4 rounded-lg border-2 transition-all ${
                selectedDecision === "DENIED"
                  ? "border-red-500 bg-red-50 text-red-700"
                  : "border-slate-200 hover:border-slate-300 text-slate-700"
              }`}
            >
              <XCircle size={20} />
              <span className="font-medium">Deny Claim</span>
            </button>

            <button
              onClick={() => setSelectedDecision("REQUEST_INFO")}
              className={`flex items-center gap-2 p-4 rounded-lg border-2 transition-all ${
                selectedDecision === "REQUEST_INFO"
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-slate-200 hover:border-slate-300 text-slate-700"
              }`}
            >
              <AlertCircle size={20} />
              <span className="font-medium">Request Info</span>
            </button>
          </div>
        </div>

        {/* Reviewer Comment */}
        <div className="mb-5">
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Reviewer Comment *
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Explain the reason for your decision..."
            rows={4}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
          <p className="mt-1 text-xs text-slate-500">Required for auditability and transparency</p>
        </div>

        {/* Submit Button */}
        <Button
          variant="primary"
          size="lg"
          onClick={handleSubmit}
          disabled={!selectedDecision || !comment.trim()}
          className="w-full"
        >
          Submit Decision
        </Button>
      </div>

      {/* Confirmation Modal */}
      <Modal
        open={showConfirm}
        onClose={() => !submitting && setShowConfirm(false)}
        title="Confirm Decision"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowConfirm(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              variant={selectedDecision === "APPROVED" ? "primary" : "danger"}
              onClick={handleConfirm}
              loading={submitting}
            >
              Confirm {selectedDecision === "APPROVED" ? "Approval" : selectedDecision === "DENIED" ? "Denial" : "Request"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Alert type={selectedDecision === "APPROVED" ? "success" : selectedDecision === "DENIED" ? "error" : "info"}>
            You are about to <strong>{selectedDecision?.toLowerCase()}</strong> this claim.
          </Alert>

          {submitError && (
            <Alert type="error" title="Submission failed">
              {submitError}
            </Alert>
          )}

          <div>
            <div className="text-sm font-medium text-slate-700 mb-1">Claim ID:</div>
            <div className="text-sm text-slate-600">{claimId}</div>
          </div>

          {aiRecommendation && (
            <div>
              <div className="text-sm font-medium text-slate-700 mb-1">AI Recommendation:</div>
              <div className="text-sm text-slate-600">{aiRecommendation}</div>
            </div>
          )}

          <div>
            <div className="text-sm font-medium text-slate-700 mb-1">Your Decision:</div>
            <div className="text-sm text-slate-600 font-semibold">{selectedDecision}</div>
          </div>

          <div>
            <div className="text-sm font-medium text-slate-700 mb-1">Your Comment:</div>
            <div className="text-sm text-slate-600 bg-slate-50 p-3 rounded border border-slate-200">
              {comment}
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
}
