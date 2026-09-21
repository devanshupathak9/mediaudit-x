import { Check } from "lucide-react";

interface Step {
  label: string;
  status: "completed" | "current" | "upcoming";
}

interface ClaimStatusTimelineProps {
  currentStatus: string;
}

export default function ClaimStatusTimeline({ currentStatus }: ClaimStatusTimelineProps) {
  const getSteps = (): Step[] => {
    const allSteps = [
      { id: "DRAFT", label: "Draft" },
      { id: "MAPPING", label: "Mapping" },
      { id: "VALIDATED", label: "Validated" },
      { id: "SUBMITTED", label: "Submitted" },
      { id: "PENDING", label: "AI Review" },
      { id: "HUMAN_REVIEW", label: "Human Review" },
      { id: "FINAL", label: "Decision" },
    ];

    const statusOrder = ["DRAFT", "MAPPING", "VALIDATED", "SUBMITTED", "PENDING", "HUMAN_REVIEW", "APPROVED", "DENIED"];
    const currentIndex = statusOrder.indexOf(currentStatus);

    return allSteps.map((step, idx) => {
      if (idx < currentIndex || (currentStatus === "APPROVED" || currentStatus === "DENIED")) {
        return { ...step, status: "completed" as const };
      } else if (
        idx === currentIndex ||
        (step.id === "HUMAN_REVIEW" && currentStatus === "PENDING") ||
        (step.id === "FINAL" && (currentStatus === "APPROVED" || currentStatus === "DENIED"))
      ) {
        return { ...step, status: "current" as const };
      } else {
        return { ...step, status: "upcoming" as const };
      }
    });
  };

  const steps = getSteps();

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-slate-800 mb-4">Claim Status</h3>
      <div className="flex items-center justify-between">
        {steps.map((step, idx) => (
          <div key={step.id} className="flex items-center">
            <div className="flex flex-col items-center">
              {/* Circle */}
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors ${
                  step.status === "completed"
                    ? "border-emerald-500 bg-emerald-500 text-white"
                    : step.status === "current"
                    ? "border-blue-600 bg-blue-600 text-white"
                    : "border-slate-300 bg-white text-slate-400"
                }`}
              >
                {step.status === "completed" ? (
                  <Check size={16} />
                ) : (
                  <span className="text-xs font-semibold">{idx + 1}</span>
                )}
              </div>
              {/* Label */}
              <span
                className={`mt-2 text-xs font-medium ${
                  step.status === "completed" || step.status === "current"
                    ? "text-slate-700"
                    : "text-slate-400"
                }`}
              >
                {step.label}
              </span>
            </div>

            {/* Connector line */}
            {idx < steps.length - 1 && (
              <div
                className={`h-0.5 w-12 mx-2 ${
                  step.status === "completed" ? "bg-emerald-500" : "bg-slate-200"
                }`}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
