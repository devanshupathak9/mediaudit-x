export default function StatusBadge({ status, aiRecommendation }: { status: string; aiRecommendation?: string }) {
  const normalized = (status || "").toUpperCase();
  const cls =
    normalized === "APPROVED"
      ? "badge-approved"
      : normalized === "DENIED"
      ? "badge-denied"
      : normalized === "REQUEST_INFO" || normalized === "PENDING"
      ? "badge-pending"
      : "badge-info";
  const label = normalized === "REQUEST_INFO" ? "Request Info" : normalized.charAt(0) + normalized.slice(1).toLowerCase();

  const ai = (aiRecommendation || "").toUpperCase();
  const aiLabel = ai === "APPROVED" ? "AI: Approve"
    : ai === "DENIED" ? "AI: Deny"
    : ai === "REQUEST_INFO" ? "AI: Request Info"
    : null;
  const aiCls = ai === "APPROVED" ? "bg-emerald-100 text-emerald-700"
    : ai === "DENIED" ? "bg-red-100 text-red-700"
    : ai === "REQUEST_INFO" ? "bg-amber-100 text-amber-700"
    : "";

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`badge ${cls}`}>{label}</span>
      {aiLabel && (
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${aiCls}`}>
          {aiLabel}
        </span>
      )}
    </span>
  );
}
