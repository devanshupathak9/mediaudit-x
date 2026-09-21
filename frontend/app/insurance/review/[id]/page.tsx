"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Clock, Play, FileText, AlertCircle, CheckCircle, User, Calendar, DollarSign, Activity } from "lucide-react";
import StatusBadge from "../../../components/StatusBadge";
import Alert from "../../../components/ui/Alert";
import LoadingSpinner from "../../../components/ui/LoadingSpinner";
import AIRecommendationCard from "../../../components/claims/AIRecommendationCard";
import ReviewerDecisionPanel from "../../../components/claims/ReviewerDecisionPanel";
import AIAgentChat from "../../../components/claims/AIAgentChat";
import CitationPanel from "../../../components/CitationPanel";
import ClaimAuditTrail from "../../../components/claims/ClaimAuditTrail";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TABS = ["Overview", "Claim Details", "AI Analysis", "Policy & Evidence", "Audit Trail"] as const;

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
  matched_policy?: any;
  trajectory_result?: any;
};

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

export default function InsuranceReviewPage() {
  const params = useParams();
  const claimId = params.id as string;

  const [claim, setClaim] = useState<any>(null);
  const [claimLoading, setClaimLoading] = useState(true);
  const [done, setDone] = useState<DoneEvent | null>(null);
  const [alerts, setAlerts] = useState<InteractionAlertData[]>([]);
  const [running, setRunning] = useState(false);
  const [adjError, setAdjError] = useState<string | null>(null);
  const [fhirClaim, setFhirClaim] = useState<any>(null);
  const [checkedForExisting, setCheckedForExisting] = useState(false);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");

  function loadClaim() {
    fetch(`${API_BASE_URL}/claims/${claimId}/claim-json`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setFhirClaim)
      .catch(() => setFhirClaim(null));
    return fetch(`${API_BASE_URL}/claims/${claimId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setClaim);
  }
  useEffect(() => {
    loadClaim().finally(() => setClaimLoading(false));
  }, [claimId]);

  // Check for existing adjudication
  useEffect(() => {
    fetch(`${API_BASE_URL}/claims/${claimId}/adjudications`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setDone(data);
      })
      .finally(() => setCheckedForExisting(true));
  }, [claimId]);

  async function runAdjudication() {
    setRunning(true);
    setAlerts([]);
    setAdjError(null);

    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/claims/${claimId}/adjudicate`, { method: "POST" });
    } catch {
      setAdjError(`Could not reach the API at ${API_BASE_URL}. Is the backend running?`);
      setRunning(false);
      return;
    }
    if (!response.ok || !response.body) {
      setAdjError(`AI analysis failed to start (HTTP ${response.status}).`);
      setRunning(false);
      return;
    }
    let finished = false;

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

        if (parsed.event === "interaction_alert") {
          setAlerts((prev) => [...prev, data]);
        } else if (parsed.event === "done") {
          finished = true;
          setDone(data);
        } else if (parsed.event === "error") {
          finished = true;
          setAdjError(data.detail || "AI analysis failed.");
        }
      }
    }
    if (!finished) setAdjError("AI analysis stopped before returning a result. Check the backend logs.");
    loadClaim().catch(() => {});
    setRunning(false);
  }

  const loading = claimLoading || !checkedForExisting;

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <LoadingSpinner size={32} message="Loading claim..." />
      </div>
    );
  }

  if (!claim) {
    return (
      <div className="card p-8 text-center">
        <p className="text-slate-600">Claim not found</p>
        <Link href="/review-queue" className="mt-2 inline-block text-blue-600 hover:underline">
          Back to Review Queue
        </Link>
      </div>
    );
  }

  const aiRec = claim?.ai_recommendation?.status || done?.status || null;

  const policyEvidence = (done?.cited_evidence || []).filter((e: any) => e.source_index === "medical-policies");
  const otherEvidence = (done?.cited_evidence || []).filter((e: any) => e.source_index !== "medical-policies");

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      {/* Header */}
      <div>
        <Link href="/review-queue" className="mb-2 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft size={14} /> Back to Review Queue
        </Link>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-slate-900">Claim {claim.claim_id}</h1>
            <StatusBadge status={claim.status} aiRecommendation={aiRec} />
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <Clock size={16} className="text-slate-400" />
              <span>Submitted: {claim.submitted_date || "N/A"}</span>
            </div>
            {!done && (
              <button
                onClick={runAdjudication}
                disabled={running}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white ${
                  running ? "cursor-default bg-slate-400" : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                <Play size={15} />
                {running ? "Analyzing..." : "Run AI Analysis"}
              </button>
            )}
          </div>
        </div>
      </div>

      {adjError && (
        <Alert type="error" title="AI analysis could not run">
          {adjError}
        </Alert>
      )}

      {/* Quick Summary Card */}
      <div className="card p-4">
        <div className="grid grid-cols-5 gap-4 text-sm">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Patient</div>
            <div className="mt-0.5 font-medium text-slate-800">{claim.patient_id}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Payer</div>
            <div className="mt-0.5 font-medium text-slate-800">{claim.payer_name}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">CPT / ICD-10</div>
            <div className="mt-0.5 font-medium text-slate-800">{claim.cpt_code} / {claim.icd10_code}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Claim Amount</div>
            <div className="mt-0.5 font-semibold text-emerald-600">${claim.claim_amount?.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Status</div>
            <div className="mt-0.5">
              <StatusBadge status={claim.status} aiRecommendation={aiRec} />
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === t
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "Overview" && (
        <div className="space-y-5">
          {/* AI Analysis Prompt or Results */}
          {!done ? (
            <div className="card flex items-center justify-between p-6">
              <div>
                <h2 className="text-base font-semibold text-slate-800 mb-1">AI Analysis Not Run</h2>
                <p className="text-sm text-slate-500">
                  Run AI analysis to get policy matching, trajectory analysis, and drug interaction detection.
                </p>
              </div>
              <button
                onClick={runAdjudication}
                disabled={running}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white ${
                  running ? "cursor-default bg-slate-400" : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                <Play size={15} />
                {running ? "Analyzing..." : "Run AI Analysis"}
              </button>
            </div>
          ) : (
            <>
              {/* AI Recommendation */}
              <AIRecommendationCard
                status={done.status}
                matchedPolicy={done.matched_policy}
                trajectoryResult={done.trajectory_result}
                evidenceCount={done.cited_evidence?.length || 0}
                interactionCount={alerts.length}
              />

              {/* Quick Stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="card p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                      <FileText size={20} className="text-blue-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-semibold text-slate-900">{done.cited_evidence?.length || 0}</div>
                      <div className="text-xs text-slate-500">Evidence Items</div>
                    </div>
                  </div>
                </div>
                <div className="card p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
                      <AlertCircle size={20} className="text-red-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-semibold text-slate-900">{alerts.length}</div>
                      <div className="text-xs text-slate-500">Drug Interactions</div>
                    </div>
                  </div>
                </div>
                <div className="card p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                      <CheckCircle size={20} className="text-emerald-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-semibold text-slate-900">
                        {done.matched_policy ? "Yes" : "No"}
                      </div>
                      <div className="text-xs text-slate-500">Policy Match</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Decision Panel, with the AI chat right beside it so the
                  reviewer can ask a question without leaving this tab. */}
              <div className="grid grid-cols-3 gap-5 items-start">
                <div className="col-span-2">
                  <ReviewerDecisionPanel
                    claimId={claim.claim_id}
                    aiRecommendation={aiRec}
                    currentStatus={claim.status}
                    reviewerComment={claim.reviewer_comment}
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
                      setClaim((prev: any) => (prev ? { ...prev, status: result.status, reviewer_comment: comment } : prev));
                    }}
                  />
                </div>
                <AIAgentChat claimId={claim.claim_id} />
              </div>
            </>
          )}
        </div>
      )}

      {tab === "Claim Details" && (
        <div className="space-y-5">
          <StructuredClaimCard fhirClaim={fhirClaim} status={claim.status} />

          {/* Patient Information */}
          <div className="card p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <User size={20} className="text-blue-600" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Patient Information</h2>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Patient ID</div>
                <div className="font-semibold text-slate-900">{claim.patient_id}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Patient Name</div>
                <div className="font-semibold text-slate-900">{claim.patient_name || "N/A"}</div>
              </div>
            </div>
          </div>

          {/* Clinical Information */}
          <div className="card p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Activity size={20} className="text-purple-600" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Clinical Information</h2>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div className="bg-purple-50 rounded-lg p-4">
                <div className="text-xs font-medium text-purple-600 mb-1">Procedure Code (CPT)</div>
                <div className="font-mono font-bold text-lg text-purple-700">{claim.cpt_code}</div>
              </div>
              <div className="bg-indigo-50 rounded-lg p-4">
                <div className="text-xs font-medium text-indigo-600 mb-1">Diagnosis Code (ICD-10)</div>
                <div className="font-mono font-bold text-lg text-indigo-700">{claim.icd10_code}</div>
              </div>
              {claim.rxnorm_code && (
                <div className="bg-teal-50 rounded-lg p-4">
                  <div className="text-xs font-medium text-teal-600 mb-1">Medication (RxNorm)</div>
                  <div className="font-mono font-bold text-lg text-teal-700">{claim.rxnorm_code}</div>
                </div>
              )}
            </div>
          </div>

          {/* Dates and Timeline */}
          <div className="card p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Calendar size={20} className="text-amber-600" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Dates & Timeline</h2>
            </div>
            <div className="grid grid-cols-3 gap-6">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Submitted Date</div>
                <div className="font-semibold text-slate-900">{claim.submitted_date || "N/A"}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Service Date</div>
                <div className="font-semibold text-slate-900">{claim.service_date || "N/A"}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Last Updated</div>
                <div className="font-semibold text-slate-900">{claim.updated_at || "N/A"}</div>
              </div>
            </div>
          </div>

          {/* Financial Information */}
          <div className="card p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                <DollarSign size={20} className="text-emerald-600" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Financial Information</h2>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div className="bg-emerald-50 border-2 border-emerald-200 rounded-lg p-6">
                <div className="text-xs font-medium text-emerald-600 mb-2">Total Claim Amount</div>
                <div className="text-3xl font-bold text-emerald-700">${claim.claim_amount?.toLocaleString()}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-6">
                <div className="text-xs font-medium text-slate-500 mb-2">Insurance Provider</div>
                <div className="text-xl font-semibold text-slate-900">{claim.payer_name}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "AI Analysis" && (
        <div className="space-y-5">
          {!done ? (
            <div className="card p-8 text-center">
              <div className="flex justify-center mb-4">
                <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center">
                  <Play size={32} className="text-slate-400" />
                </div>
              </div>
              <h2 className="text-lg font-semibold text-slate-900 mb-2">No AI Analysis Yet</h2>
              <p className="text-sm text-slate-600 mb-6">
                Click "Run AI Analysis" to start the adjudication process.
              </p>
            </div>
          ) : (
            <>
              {/* Generated Decision Letter */}
              <div className="card p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <FileText size={20} className="text-blue-600" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">AI-Generated Decision Letter</h2>
                    <p className="text-xs text-slate-500">Based on policy matching and evidence analysis</p>
                  </div>
                </div>
                <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-lg p-6 border border-slate-200">
                  <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 font-sans">
                    {done.generated_letter}
                  </pre>
                </div>
              </div>

              {/* AI Recommendation Summary */}
              <div className={`card p-6 border-2 ${
                done.status === "APPROVE" ? "border-emerald-200 bg-emerald-50" :
                done.status === "DENY" ? "border-red-200 bg-red-50" :
                "border-amber-200 bg-amber-50"
              }`}>
                <h3 className="text-sm font-semibold text-slate-700 mb-2">AI Recommendation</h3>
                <div className={`text-2xl font-bold ${
                  done.status === "APPROVE" ? "text-emerald-700" :
                  done.status === "DENY" ? "text-red-700" :
                  "text-amber-700"
                }`}>
                  {done.status}
                </div>
                <p className="text-xs text-slate-600 mt-2">
                  This is an advisory recommendation. Final decision is at the reviewer's discretion.
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "Policy & Evidence" && (
        <div className="space-y-5">
          {!done ? (
            <div className="card p-8 text-center">
              <p className="text-sm text-slate-600">
                Run AI analysis to see matched policies and evidence.
              </p>
            </div>
          ) : (
            <>
              {/* Drug Interaction Alerts */}
              {alerts.length > 0 && (
                <div className="card p-6 border-2 border-red-200 bg-red-50">
                  <div className="flex items-start gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                      <AlertCircle size={20} className="text-red-600" />
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-red-900">Drug Interaction Findings</h3>
                      <p className="text-xs text-red-700 mt-1">{alerts.length} potential interaction(s) detected</p>
                    </div>
                  </div>
                  <div className="space-y-3">
                    {alerts.map((a, i) => (
                      <div key={i} className="bg-white rounded-lg p-4 border border-red-200">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            a.severity === "MAJOR" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                          }`}>
                            {a.severity}
                          </span>
                        </div>
                        <div className="text-sm text-slate-800 mb-1">
                          <strong>{a.drug_a}</strong> + <strong>{a.drug_b}</strong>
                        </div>
                        <div className="text-xs text-slate-600">{a.mechanism}</div>
                        {a.fda_citation && (
                          <div className="text-xs text-slate-500 mt-2">
                            <span className="font-medium">Source:</span> {a.fda_citation}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Matched Policy */}
              {done.matched_policy && (
                <div className="card p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                      <CheckCircle size={20} className="text-emerald-600" />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-slate-900">Matched Policy</h2>
                      <p className="text-xs text-slate-500">Coverage policy identified for this claim</p>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-lg border-2 border-emerald-200 p-5 mb-4">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="text-sm font-bold text-slate-900 mb-1">
                          {done.matched_policy.title}
                        </div>
                        <div className="text-xs text-slate-600">
                          <span className="inline-block bg-white px-2 py-1 rounded font-mono text-xs">
                            {done.matched_policy.policy_id}
                          </span>
                        </div>
                      </div>
                      {done.matched_policy.step_therapy_required && (
                        <span className="px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-xs font-semibold">
                          Step Therapy Required
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-600 mb-2">
                      <strong className="text-slate-700">Payer:</strong> {done.matched_policy.payer_name}
                    </div>
                    <div className="text-sm text-slate-700 leading-relaxed bg-white/50 rounded p-3 border border-emerald-100">
                      <strong className="text-emerald-700 text-xs block mb-1">Clinical Indications:</strong>
                      {done.matched_policy.clinical_indications}
                    </div>
                  </div>

                  {policyEvidence.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-slate-800 mb-3">Supporting Evidence</h3>
                      <CitationPanel evidence={policyEvidence} />
                    </div>
                  )}
                </div>
              )}

              {/* Clinical Evidence */}
              {otherEvidence.length > 0 && (
                <div className="card p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                      <FileText size={20} className="text-blue-600" />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-slate-900">Clinical Evidence</h2>
                      <p className="text-xs text-slate-500">{otherEvidence.length} evidence item(s) found</p>
                    </div>
                  </div>
                  <CitationPanel evidence={otherEvidence} />
                </div>
              )}

              {/* No Policy Match Message */}
              {!done.matched_policy && policyEvidence.length === 0 && otherEvidence.length === 0 && (
                <div className="card p-8 text-center">
                  <p className="text-sm text-slate-600">
                    No policy matches or clinical evidence found for this claim.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === "Audit Trail" && <ClaimAuditTrail claimId={claim.claim_id} />}
    </div>
  );
}

function citationText(entry: any): string | null {
  const ext = (entry?.extension || []).find((e: any) => String(e.url).endsWith("/source-citation"));
  if (!ext) return null;
  const part = (name: string) => ext.extension?.find((e: any) => e.url === name);
  const docId = part("docId")?.valueString;
  const source = docId === "hospital-form" ? "hospital form" : `${docId} p${part("page")?.valueInteger}`;
  return `${source}: "${part("quote")?.valueString}"`;
}

function StructuredClaimCard({ fhirClaim, status }: { fhirClaim: any; status: string }) {
  if (!fhirClaim) {
    return (
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-1">Structured Claim (FHIR R4)</h2>
        <p className="text-sm text-slate-500">
          Not received yet (claim is {status}). It is built once the codes have been extracted from the uploaded
          documents and the claim is submitted.
        </p>
      </div>
    );
  }
  const rows: { kind: string; code: string; display: string; cite: string | null }[] = [
    ...(fhirClaim.diagnosis || []).map((d: any) => ({
      kind: d.sequence === 1 ? "ICD-10 (primary)" : "ICD-10",
      code: d.diagnosisCodeableConcept?.coding?.[0]?.code,
      display: d.diagnosisCodeableConcept?.coding?.[0]?.display || "",
      cite: citationText(d),
    })),
    ...(fhirClaim.item || []).map((i: any) => ({
      kind: i.sequence === 1 ? "CPT (primary)" : "CPT",
      code: i.productOrService?.coding?.[0]?.code,
      display: i.productOrService?.coding?.[0]?.display || "",
      cite: citationText(i),
    })),
    ...(fhirClaim.supportingInfo || [])
      .filter((s: any) => s.category?.text === "medication")
      .map((s: any) => ({
        kind: "Medication",
        code: s.code?.coding?.[0]?.code || "—",
        display: s.code?.text || "",
        cite: citationText(s),
      })),
  ];
  return (
    <div className="card p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Structured Claim (FHIR R4) — as received</h2>
        <span className="text-xs text-slate-500">
          {fhirClaim.insurer?.display} · {fhirClaim.patient?.reference}
          {fhirClaim.total ? ` · ${fhirClaim.total.currency} ${Number(fhirClaim.total.value).toLocaleString()}` : ""}
        </span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
            <th className="py-1 pr-3">Type</th>
            <th className="py-1 pr-3">Code</th>
            <th className="py-1 pr-3">Description</th>
            <th className="py-1">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={idx} className="border-t border-slate-100 align-top">
              <td className="py-2 pr-3 text-slate-500">{r.kind}</td>
              <td className="py-2 pr-3 font-mono font-semibold text-slate-900">{r.code}</td>
              <td className="py-2 pr-3 text-slate-700">{r.display}</td>
              <td className="py-2 text-xs text-slate-500">{r.cite || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-blue-600">View claim JSON</summary>
        <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-100">
          {JSON.stringify(fhirClaim, null, 2)}
        </pre>
      </details>
    </div>
  );
}
