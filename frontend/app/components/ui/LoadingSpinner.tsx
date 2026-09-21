import { Loader2 } from "lucide-react";

interface LoadingSpinnerProps {
  size?: number;
  className?: string;
  message?: string;
}

export default function LoadingSpinner({ size = 24, className = "", message }: LoadingSpinnerProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 ${className}`}>
      <Loader2 size={size} className="animate-spin text-blue-600 mb-3" />
      {message && <p className="text-sm text-slate-500">{message}</p>}
    </div>
  );
}
