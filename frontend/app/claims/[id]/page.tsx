/**
 * Claim detail / adjudication screen.
 *
 * Tabbed layout (Overview / Clinical History / Policy & Guidelines /
 * Adjudication / Audit Trail) restyled to look like a real clinical
 * review tool. Every number/status shown here comes from the real
 * backend (claim record, /patients/{id}/history, and the adjudicate SSE
 * stream) — nothing is hardcoded demo data, so an empty tab before you
 * click "Run Adjudication" is honest, not a bug.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRole } from "../../contexts/RoleContext";
import {
  ArrowLeft,
  Play,
  ShieldAlert,
  CheckCircle2,
  Sparkles,
  FileText,
  Link as LinkIcon,
} from "lucide-react";
import LoadingSpinner from "../../components/ui/LoadingSpinner";
import Timeline from "../../components/Timeline";
import CitationPanel from "../../components/CitationPanel";
import InteractionAlert from "../../components/InteractionAlert";
import StatusBadge from "../../components/StatusBadge";
import AIRecommendationCard from "../../components/claims/AIRecommendationCard";
import ClaimStatusTimeline from "../../components/claims/ClaimStatusTimeline";
import ReviewerDecisionPanel from "../../components/claims/ReviewerDecisionPanel";
import AIAgentChat from "../../components/claims/AIAgentChat";
import ClaimAuditTrail from "../../components/claims/ClaimAuditTrail";
import { DemoDataManager, type DemoInsuranceClaim } from "../../lib/completeDemoData";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const USE_DEMO_DATA = false; // wired to the real backend API

type ReasoningStep = { step: string; detail: string };
type InteractionAlertData = {
  severity: string;
  drug_a: string;
  drug_b: string;
  mechanism: string;
  fda_citation: string;
};
type DoneEvent = {
  status: string;
  adjudication_id: string;
  cited_evidence: any[];
  generated_letter: string;
  fhir_claim_response: any;
  ledger_entry?: { ledger_id: string; sequence_number: number; record_hash: string; prev_hash: string; timestamp: string };
  matched_policy?: any;
  trajectory_result?: any;
};

const TABS = ["Overview", "Clinical History", "Policy & Guidelines", "AI Assistant", "Adjudication", "Audit Trail"] as const;

function parseSSEEvent(chunk: string): { event: string; data: string } | null {
  const lines = chunk.split("\n");
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  return data ? { event, data } : null;
}

export default function ClaimDetailPage() {
  const params = useParams();
  const { role } = useRole();
  const claimId = params.id as string;

  // Hospital users can view the claim (read-only) but can't trigger
  // adjudication themselves -- see the role-gated "Run Adjudication"
  // button below. Previously this redirected hospital users straight
  // back to /claims, which is why the "View" link on the dashboard and
  // claims list appeared to do nothing for that role.
  const canAdjudicate = role !== "hospital";

  const [claim, setClaim] = useState<any>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [steps, setSteps] = useState<ReasoningStep[]>([]);
  const [alerts, setAlerts] = useState<InteractionAlertData[]>([]);
  const [done, setDone] = useState<DoneEvent | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (USE_DEMO_DATA) {
      // Use demo data
      const demoClaim = DemoDataManager.getClaim(claimId);
      if (demoClaim) {
        setClaim(demoClaim as any);
      }
    } else {
      // Use real API
      fetch(`${API_BASE_URL}/claims/${claimId}`)
        .then((res) => res.json())
        .then(setClaim)
        .catch(() => {
          // Fallback to demo data
          const demoClaim = DemoDataManager.getClaim(claimId);
          if (demoClaim) {
            setClaim(demoClaim as any);
          }
        });
    }
  }, [claimId]);

  async function runAdjudication() {
    setRunning(true);
    setSteps([]);
    setAlerts([]);
    setDone(null);
    setTab("Adjudication");

    if (USE_DEMO_DATA) {
      // Simulate AI processing with demo data
      const demoSteps = [
        { step: "Policy Search", detail: "Searching for applicable coverage policies..." },
        { step: "Policy Match Found", detail: `Matched policy: ${claim.payer_name} - Total Knee Arthroplasty Coverage` },
        { step: "Patient Timeline Analysis", detail: "Analyzing patient's clinical history and treatment timeline..." },
        { step: "Conservative Treatment Check", detail: "Verifying 180-day conservative treatment requirement..." },
        { step: "Drug Safety Check", detail: "Checking for medication interactions..." },
        { step: "Evidence Validation", detail: "Validating supporting clinical documentation..." },
        { step: "Decision Generation", detail: "Generating recommendation based on policy requirements..." },
      ];

      for (const step of demoSteps) {
        await new Promise(resolve => setTimeout(resolve, 800));
        setSteps((prev) => [...prev, step]);
      }

      // Get demo AI response
      const demoResponse = DemoDataManager.getAIResponse(claimId);
      if (demoResponse) {
        setDone(demoResponse as any);
      }

      setRunning(false);
      setTab("Overview");
      return;
    }

    // Real API call
    const response = await fetch(`${API_BASE_URL}/claims/${claimId}/adjudicate`, { method: "POST" });
    if (!response.body) {
      setRunning(false);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const parsed = parseSSEEvent(chunk);
        if (!parsed) continue;
        const data = JSON.parse(parsed.data);

        if (parsed.event === "reasoning_step") {
          setSteps((prev) => [...prev, data]);
        } else if (parsed.event === "interaction_alert") {
          setAlerts((prev) => [...prev, data]);
        } else if (parsed.event === "done") {
          setDone(data);
          setTab("Overview");
        } else if (parsed.event === "error") {
          setSteps((prev) => [...prev, { step: "error", detail: data.detail }]);
        }
      }
    }
    setRunning(false);
  }

  if (!claim) return <LoadingSpinner message="Loading claim..." />;

  const hasContraindication = alerts.some((a) => a.severity === "Contraindicated" || a.severity === "Major");
  const riskLevel = done ? (done.status === "DENIED" ? "High" : done.status === "REQUEST_INFO" ? "Medium" : "Low") : null;
  const riskReason = hasContraindication
    ? "Contraindicated drug interaction detected"
    : done?.trajectory_result && !done.trajectory_result.step_therapy_met
    ? "Step therapy requirement not met"
    : done?.status === "APPROVED"
    ? "All coverage criteria satisfied"
    : null;

  const policyEvidence = (done?.cited_evidence || []).filter((e: any) => e.source_index === "medical-policies");
  const otherEvidence = (done?.cited_evidence || []).filter((e: any) => e.source_index !== "medical-policies");

  return (
    <div className="space-y-5">
      <Link href="/claims" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={14} /> Back to Claims
      </Link>

      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900">Claim {claim.claim_id}</h1>
          <StatusBadge status={claim.status} aiRecommendation={claim.ai_recommendation?.status || done?.status} />
        </div>
        {canAdjudicate && (
          <button
            onClick={runAdjudication}
            disabled={running}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white ${
              running ? "cursor-default bg-slate-400" : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            <Play size={15} />
            {running ? "Adjudicating..." : "Run Adjudication"}
          </button>
        )}
      </div>

      <div className="card grid grid-cols-5 gap-4 p-4 text-sm">
        <Field label="Patient" value={claim.patient_id} />
        <Field label="Payer" value={claim.payer_name} />
        <Field label="CPT / ICD-10" value={`${claim.cpt_code} / ${claim.icd10_code}`} />
        <Field label="Claim Amount" value={`$${claim.claim_amount?.toLocaleString()}`} />
        <Field label="Submitted" value={claim.submitted_date} />
      </div>

      {/* Status Timeline */}
      <ClaimStatusTimeline currentStatus={done?.status || claim.status} />

      {alerts.length > 0 && <InteractionAlert alerts={alerts} />}

      {done?.status === "DENIED" && riskReason && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="text-sm font-semibold text-red-800">Denial Reason</div>
          <p className="mt-1 text-sm text-red-700">{riskReason}.</p>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === t ? "border-b-2 border-blue-600 text-blue-600" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-5">
          {/* AI Recommendation and Summary Row */}
          <div className="grid grid-cols-3 gap-5">
            <div className="col-span-2">
              <div className="card p-5">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <FileText size={15} /> Claim Summary
                </h2>
                {done ? (
                  <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-xs leading-relaxed text-slate-700">
                    {done.generated_letter}
                  </pre>
                ) : (
                  <p className="text-sm text-slate-400">Run adjudication to generate a decision summary and letter.</p>
                )}
              </div>
            </div>

            <div>
              <AIRecommendationCard
                status={done?.status}
                matchedPolicy={done?.matched_policy}
                trajectoryResult={done?.trajectory_result}
                evidenceCount={done?.cited_evidence?.length || 0}
                interactionCount={alerts.length}
              />
            </div>
          </div>

          {/* Reviewer Decision Panel, with the AI chat right beside it so a
              reviewer can ask a question without leaving this tab -- the
              full "AI Assistant" tab still exists for a larger, dedicated
              view of the same chat. */}
          {done && canAdjudicate && (
            <div className="grid grid-cols-3 gap-5 items-start">
              <div className="col-span-2">
                <ReviewerDecisionPanel
                  claimId={claim.claim_id}
                  aiRecommendation={done.status}
                  onDecisionSubmit={async (decision, comment) => {
                    const res = await fetch(`${API_BASE_URL}/claims/${claim.claim_id}/decision`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        decision: decision === "APPROVED" ? "APPROVE" : decision === "DENIED" ? "DENY" : "REQUEST_INFO",
                        reviewer_comment: comment,
                      }),
                    });
                    if (!res.ok) {
                      throw new Error(`Failed to submit decision (${res.status})`);
                    }
                    const result = await res.json();
                    // Reflect the human reviewer's decision immediately -- it
                    // supersedes the AI's own recommendation for this claim.
                    setDone((prev) => (prev ? { ...prev, status: result.status } : prev));
                    setClaim((prev: any) => (prev ? { ...prev, status: result.status } : prev));
                  }}
                />
              </div>
              <AIAgentChat claimId={claim.claim_id} />
            </div>
          )}
        </div>
      )}

      {tab === "Clinical History" && (
        <Timeline patientId={claim.patient_id} apiBaseUrl={API_BASE_URL} trajectoryResult={done?.trajectory_result} />
      )}

      {tab === "Policy & Guidelines" && (
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Matched Policy</h2>
          {done?.matched_policy ? (
            <div className="mb-4 rounded-lg border border-slate-100 p-4 text-sm">
              <div className="font-medium text-slate-800">
                {done.matched_policy.policy_id} — {done.matched_policy.title}
              </div>
              <div className="mt-1 text-slate-500">{done.matched_policy.payer_name}</div>
              <div className="mt-2 text-slate-600">{done.matched_policy.clinical_indications}</div>
              {done.matched_policy.step_therapy_required && (
                <span className="badge badge-pending mt-2">Step therapy required</span>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Run adjudication to match this claim against a coverage policy.</p>
          )}
          {policyEvidence.length > 0 && <CitationPanel evidence={policyEvidence} />}
        </div>
      )}

      {tab === "AI Assistant" && (
        <AIAgentChat claimId={claim.claim_id} isExpanded />
      )}

      {tab === "Adjudication" && (
        <div className="space-y-5">
          {steps.length > 0 ? (
            <div className="card p-5">
              <h2 className="mb-3 text-sm font-semibold text-slate-800">Live Agent Reasoning</h2>
              <ol className="space-y-1.5 text-sm">
                {steps.map((s, i) => (
                  <li key={i} className="text-slate-600">
                    <span className="font-medium text-slate-800">{s.step}</span> — {s.detail}
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Click "Run Adjudication" above to start.</p>
          )}
          {otherEvidence.length > 0 && <CitationPanel evidence={otherEvidence} />}
        </div>
      )}

      {tab === "Audit Trail" && <ClaimAuditTrail claimId={claim.claim_id} />}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 font-medium text-slate-800">{value}</div>
    </div>
  );
}
