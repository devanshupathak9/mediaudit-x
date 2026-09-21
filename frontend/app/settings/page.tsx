"use client";
import { Settings as SettingsIcon } from "lucide-react";
import ComingSoon from "../components/ComingSoon";

export default function SettingsPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
      <ComingSoon
        icon={SettingsIcon}
        title="Settings"
        description="Elastic connection, model, and threshold configuration currently live in backend/.env — an in-app settings screen isn't built yet."
      />
    </div>
  );
}
