"use client";

type Alert = {
  severity: string;
  drug_a: string;
  drug_b: string;
  mechanism: string;
  fda_citation: string;
};

const SEVERITY_STYLE: Record<string, { bg: string; border: string; text: string; label: string }> = {
  Contraindicated: { bg: "bg-red-50", border: "border-red-300", text: "text-red-700", label: "CONTRAINDICATED" },
  Major: { bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-700", label: "MAJOR" },
  Moderate: { bg: "bg-yellow-50", border: "border-yellow-300", text: "text-yellow-700", label: "MODERATE" },
};

export default function InteractionAlert({ alerts }: { alerts: Alert[] }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const style = SEVERITY_STYLE[alert.severity] ?? {
          bg: "bg-slate-50",
          border: "border-slate-300",
          text: "text-slate-700",
          label: alert.severity?.toUpperCase() ?? "INTERACTION",
        };
        return (
          <div key={i} className={`rounded-xl border-2 ${style.border} ${style.bg} p-4`}>
            <div className={`text-xs font-semibold tracking-wide ${style.text}`}>{style.label} DRUG INTERACTION</div>
            <div className="mt-1 text-base font-semibold text-slate-800">
              {alert.drug_a} + {alert.drug_b}
            </div>
            <div className="mt-1 text-sm text-slate-600">{alert.mechanism}</div>
            <div className="mt-1 text-xs text-slate-400">{alert.fda_citation}</div>
          </div>
        );
      })}
    </div>
  );
}
