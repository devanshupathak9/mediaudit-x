"use client";

import { useEffect, useState } from "react";

type HistoryEvent = {
  id: string;
  encounter_id?: string;
  timestamp: string;
  resource_type: string;
  code_display?: string;
  clinician_notes?: string;
};

type TrajectoryResult = {
  earliest_therapy?: string;
  latest_therapy?: string;
  step_therapy_met?: boolean;
  therapy_duration_days?: number;
  required_duration_days?: number;
};

export default function Timeline({
  patientId,
  apiBaseUrl,
  trajectoryResult,
}: {
  patientId: string;
  apiBaseUrl: string;
  trajectoryResult?: TrajectoryResult | null;
}) {
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!patientId) return;
    fetch(`${apiBaseUrl}/patients/${patientId}/history`)
      .then((res) => res.json())
      .then((data) => {
        setEvents(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [patientId, apiBaseUrl]);

  if (loading) return <p className="text-sm text-slate-400">Loading patient history...</p>;
  if (events.length === 0) return <p className="text-sm text-slate-400">No history found for {patientId}.</p>;

  const times = events.map((e) => new Date(e.timestamp).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = Math.max(max - min, 1);

  const highlightStart = trajectoryResult?.earliest_therapy ? new Date(trajectoryResult.earliest_therapy).getTime() : null;
  const highlightEnd = trajectoryResult?.latest_therapy ? new Date(trajectoryResult.latest_therapy).getTime() : null;

  return (
    <div className="card p-5">
      <h2 className="mb-1 text-sm font-semibold text-slate-800">Patient Timeline — {patientId}</h2>

      {trajectoryResult && (
        <p className={`mb-3 text-sm font-medium ${trajectoryResult.step_therapy_met ? "text-emerald-600" : "text-red-600"}`}>
          Step therapy {trajectoryResult.step_therapy_met ? "MET" : "NOT MET"}: {trajectoryResult.therapy_duration_days ?? 0} of{" "}
          {trajectoryResult.required_duration_days ?? 0} required day(s)
        </p>
      )}

      <div className="relative h-14 rounded-lg bg-slate-50">
        {highlightStart !== null && highlightEnd !== null && (
          <div
            className={`absolute inset-y-0 rounded-lg ${
              trajectoryResult?.step_therapy_met ? "bg-emerald-100" : "bg-red-100"
            }`}
            style={{
              left: `${((highlightStart - min) / span) * 100}%`,
              width: `${Math.max(((highlightEnd - highlightStart) / span) * 100, 1)}%`,
            }}
            title="Measured conservative-therapy window"
          />
        )}
        {events.map((event) => {
          const t = new Date(event.timestamp).getTime();
          const left = ((t - min) / span) * 100;
          return (
            <div
              key={event.id}
              title={`${event.timestamp} — ${event.code_display ?? event.resource_type}`}
              className={`absolute top-5 h-2.5 w-2.5 -translate-x-1/2 rounded-full ${
                event.resource_type === "MedicationRequest" ? "bg-purple-500" : "bg-blue-500"
              }`}
              style={{ left: `${left}%` }}
            />
          );
        })}
      </div>

      <ul className="mt-4 space-y-1 text-sm text-slate-600">
        {events.map((event) => (
          <li key={event.id}>
            <span className="text-slate-400">{new Date(event.timestamp).toLocaleDateString()}</span> — {event.resource_type}:{" "}
            {event.code_display}
            {event.clinician_notes ? ` — "${event.clinician_notes}"` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
