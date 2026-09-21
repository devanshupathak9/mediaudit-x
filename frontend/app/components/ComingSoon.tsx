import { LucideIcon } from "lucide-react";

export default function ComingSoon({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white py-24 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
        <Icon size={22} className="text-blue-600" />
      </div>
      <h2 className="text-base font-semibold text-slate-800">{title}</h2>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      <span className="mt-4 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
        Build live — not implemented yet
      </span>
    </div>
  );
}
