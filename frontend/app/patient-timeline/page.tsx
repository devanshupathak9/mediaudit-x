"use client";
import { History } from "lucide-react";
import ComingSoon from "../components/ComingSoon";

export default function PatientTimelinePage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-900">Patient Timeline</h1>
      <p className="text-sm text-slate-500">
        A standalone patient search/timeline view isn't built yet — for now, open a claim from{" "}
        <a href="/claims" className="text-blue-600 hover:underline">Claims</a> to see that patient's real timeline
        (backed by GET /patients/&#123;id&#125;/history) on the claim detail page.
      </p>
      <ComingSoon
        icon={History}
        title="Standalone Patient Search"
        description="Search across all patients by name/ID and browse their full longitudinal record outside the context of a single claim."
      />
    </div>
  );
}
