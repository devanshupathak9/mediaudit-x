import { LucideIcon } from "lucide-react";

export default function StatCard({
  icon: Icon,
  iconBg,
  iconColor,
  label,
  value,
  trend,
  trendUp,
}: {
  icon: LucideIcon;
  iconBg: string;
  iconColor: string;
  label: string;
  value: string | number;
  trend?: string;
  trendUp?: boolean;
}) {
  return (
    <div className="card flex items-start justify-between p-4">
      <div>
        <div className="text-sm text-slate-500">{label}</div>
        <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
        {trend && (
          <div className={`mt-1 text-xs font-medium ${trendUp ? "text-emerald-600" : "text-red-500"}`}>
            {trendUp ? "↑" : "↓"} {trend}
          </div>
        )}
      </div>
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${iconBg}`}>
        <Icon size={18} className={iconColor} />
      </div>
    </div>
  );
}
