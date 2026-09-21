import { AlertCircle, CheckCircle2, Info, XCircle } from "lucide-react";

type AlertType = "success" | "error" | "warning" | "info";

interface AlertProps {
  type: AlertType;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export default function Alert({ type, title, children, className = "" }: AlertProps) {
  const icons = {
    success: CheckCircle2,
    error: XCircle,
    warning: AlertCircle,
    info: Info,
  };

  const styles = {
    success: "bg-emerald-50 border-emerald-200 text-emerald-800",
    error: "bg-red-50 border-red-200 text-red-800",
    warning: "bg-amber-50 border-amber-200 text-amber-800",
    info: "bg-blue-50 border-blue-200 text-blue-800",
  };

  const iconColors = {
    success: "text-emerald-600",
    error: "text-red-600",
    warning: "text-amber-600",
    info: "text-blue-600",
  };

  const Icon = icons[type];

  return (
    <div className={`rounded-lg border p-4 ${styles[type]} ${className}`}>
      <div className="flex gap-3">
        <Icon size={18} className={`flex-shrink-0 mt-0.5 ${iconColors[type]}`} />
        <div className="flex-1">
          {title && <div className="font-semibold mb-1 text-sm">{title}</div>}
          <div className="text-sm">{children}</div>
        </div>
      </div>
    </div>
  );
}
