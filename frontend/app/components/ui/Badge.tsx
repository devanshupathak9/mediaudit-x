type BadgeVariant = "success" | "error" | "warning" | "info" | "neutral";

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}

export default function Badge({ variant, children, dot, className = "" }: BadgeProps) {
  const styles = {
    success: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    error: "bg-red-50 text-red-700 ring-red-600/20",
    warning: "bg-amber-50 text-amber-700 ring-amber-600/20",
    info: "bg-blue-50 text-blue-700 ring-blue-600/20",
    neutral: "bg-slate-50 text-slate-700 ring-slate-600/20",
  };

  const dotColors = {
    success: "bg-emerald-500",
    error: "bg-red-500",
    warning: "bg-amber-500",
    info: "bg-blue-500",
    neutral: "bg-slate-500",
  };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${styles[variant]} ${className}`}>
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dotColors[variant]}`} />}
      {children}
    </span>
  );
}
