import { CheckCircle2, AlertTriangle, AlertCircle, FileQuestion } from "lucide-react";

interface AIRecommendationCardProps {
  status?: string;
  matchedPolicy?: any;
  trajectoryResult?: any;
  evidenceCount?: number;
  interactionCount?: number;
}

export default function AIRecommendationCard({
  status,
  matchedPolicy,
  trajectoryResult,
  evidenceCount = 0,
  interactionCount = 0,
}: AIRecommendationCardProps) {
  if (!status) {
    return (
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">AI Review</h2>
        <p className="text-sm text-slate-500">Run adjudication to see AI recommendation.</p>
      </div>
    );
  }

  const getRecommendationDisplay = () => {
    switch (status) {
      case "APPROVED":
      case "APPROVE":
        return {
          label: "APPROVE RECOMMENDED",
          color: "text-emerald-700",
          bgColor: "bg-emerald-50",
          borderColor: "border-emerald-200",
          icon: CheckCircle2,
          iconColor: "text-emerald-600",
        };
      case "DENIED":
      case "DENY":
        return {
          label: "DENY RECOMMENDED",
          color: "text-red-700",
          bgColor: "bg-red-50",
          borderColor: "border-red-200",
          icon: AlertTriangle,
          iconColor: "text-red-600",
        };
      case "REQUEST_INFO":
        return {
          label: "REQUEST INFORMATION",
          color: "text-blue-700",
          bgColor: "bg-blue-50",
          borderColor: "border-blue-200",
          icon: FileQuestion,
          iconColor: "text-blue-600",
        };
      default:
        return {
          label: "HUMAN REVIEW REQUIRED",
          color: "text-amber-700",
          bgColor: "bg-amber-50",
          borderColor: "border-amber-200",
          icon: AlertCircle,
          iconColor: "text-amber-600",
        };
    }
  };

  const display = getRecommendationDisplay();
  const Icon = display.icon;

  return (
    <div className={`card border-2 ${display.borderColor} ${display.bgColor} p-5`}>
      <div className="flex items-start gap-3 mb-4">
        <div className={`p-2 rounded-lg bg-white ${display.iconColor}`}>
          <Icon size={20} />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">AI Recommendation</h2>
          <div className={`text-lg font-bold ${display.color}`}>{display.label}</div>
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-600">Policy matched:</span>
          <span className="font-medium text-slate-800">
            {matchedPolicy?.policy_id || "None"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-600">Evidence sources:</span>
          <span className="font-medium text-slate-800">{evidenceCount}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-600">Drug interactions:</span>
          <span className={`font-medium ${interactionCount > 0 ? "text-red-600" : "text-emerald-600"}`}>
            {interactionCount > 0 ? `${interactionCount} found` : "None found"}
          </span>
        </div>
        {trajectoryResult && (
          <div className="flex justify-between">
            <span className="text-slate-600">Step therapy:</span>
            <span className={`font-medium ${trajectoryResult.step_therapy_met ? "text-emerald-600" : "text-slate-600"}`}>
              {trajectoryResult.step_therapy_met ? "Satisfied" : "Insufficient evidence"}
            </span>
          </div>
        )}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-200">
        <p className="text-xs text-slate-600">
          ⚠️ AI recommendation is advisory only. Final decision requires reviewer approval.
        </p>
      </div>
    </div>
  );
}
