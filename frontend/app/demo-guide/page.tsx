"use client";

import Link from "next/link";
import { CheckCircle, ArrowRight, PlayCircle, Users, Building2 } from "lucide-react";
import Button from "../components/ui/Button";
import Alert from "../components/ui/Alert";

export default function DemoGuidePage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-100">
            <PlayCircle size={24} className="text-blue-600" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-semibold text-slate-900 mb-2">Demo Guide - Complete End-to-End Flow</h1>
            <p className="text-slate-600">
              Test the complete MediAudit-X workflow from hospital claim creation to insurance review and approval.
              All data is pre-loaded and ready to test.
            </p>
          </div>
        </div>
      </div>

      <Alert type="success" title="Demo Data Loaded">
        Complete demo scenarios are available with realistic patient data, treatment timelines, and policy requirements.
        No backend required - all data works in the browser!
      </Alert>

      {/* Hospital Flow */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Building2 size={20} className="text-blue-600" />
          <h2 className="text-xl font-semibold text-slate-900">Part 1: Hospital Flow (5-7 minutes)</h2>
        </div>

        <div className="space-y-4">
          <Step
            number={1}
            title="Switch to Hospital Role"
            description="Click the 'Switch to Hospital' button at the bottom of the sidebar"
          />

          <Step
            number={2}
            title="Create New Claim"
            description="Click 'Create Claim' in sidebar or 'Create New Claim' button on dashboard"
            link="/hospital/create-claim"
          />

          <Step
            number={3}
            title="Fill in Patient & Treatment Details"
            description="Enter patient information, treatment details, diagnosis, procedures, medications, and billing information. Sample data:"
            details={[
              "Patient: John Doe (auto-fill available)",
              "Diagnosis: Severe osteoarthritis of right knee",
              "Procedure: Total knee arthroplasty",
              "Treatment: 6+ months physical therapy, failed conservative treatment",
            ]}
          />

          <Step
            number={4}
            title="Generate Claim Report with AI"
            description="Click 'Generate Claim Report with AI' button. Watch AI process your input and generate:"
            details={[
              "✓ Standardized medical codes (ICD-10, CPT, RxNorm)",
              "✓ Policy match identification",
              "✓ Formal claim letter",
              "✓ Supporting evidence summary",
            ]}
          />

          <Step
            number={5}
            title="Review Generated Report"
            description="Review the AI-generated claim report showing all standardized codes, matched policy, and formal letter"
          />

          <Step
            number={6}
            title="Approve & Submit to Insurance"
            description="Click 'Approve & Submit to Insurance' button. The claim is now sent to the insurance company for review."
          />
        </div>
      </div>

      {/* Insurance Flow */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Users size={20} className="text-purple-600" />
          <h2 className="text-xl font-semibold text-slate-900">Part 2: Insurance Reviewer Flow (10-15 minutes)</h2>
        </div>

        <div className="space-y-4">
          <Step
            number={7}
            title="Switch to Insurance Reviewer Role"
            description="Click 'Switch to Insurance' button in sidebar footer"
          />

          <Step
            number={8}
            title="Open Review Queue"
            description="Navigate to Review Queue from sidebar to see all claims pending review"
            link="/review-queue"
            details={[
              "Filter by AI recommendation",
              "Search by claim ID or patient",
              "See stats dashboard",
            ]}
          />

          <Step
            number={9}
            title="Open Demo Claim CLM-2026-00142"
            description="Click 'Review' on claim CLM-2026-00142 (John Doe - Knee Replacement)"
            link="/claims/CLM-2026-00142"
          />

          <Step
            number={10}
            title="Review Status Timeline"
            description="See the claim's workflow progress visualization showing all completed stages"
          />

          <Step
            number={11}
            title="Run AI Adjudication"
            description="Click 'Run Adjudication' button to trigger AI analysis. Watch live streaming of:"
            details={[
              "Policy search and matching",
              "Patient timeline analysis",
              "Conservative treatment verification",
              "Drug safety checks",
              "Evidence validation",
            ]}
          />

          <Step
            number={12}
            title="Review AI Recommendation"
            description="See the AI Recommendation Card showing APPROVE RECOMMENDED with evidence summary"
          />

          <Step
            number={13}
            title="Explore Clinical History Tab"
            description="Click 'Clinical History' tab to see patient's complete treatment timeline:"
            details={[
              "187 days of physical therapy documented",
              "MRI showing severe degeneration",
              "Failed conservative treatment",
            ]}
          />

          <Step
            number={14}
            title="Check Policy Requirements (Policy & Guidelines Tab)"
            description="View matched policy and requirement status:"
            details={[
              "✓ Diagnosis: SATISFIED",
              "✓ Conservative Treatment: SATISFIED (187 days > 180 days required)",
              "✓ Imaging Evidence: SATISFIED",
              "✓ All requirements met",
            ]}
          />

          <Step
            number={15}
            title="Use AI Assistant (AI Assistant Tab)"
            description="Click 'AI Assistant' tab and ask questions:"
            details={[
              "Q: 'Was the conservative treatment requirement satisfied?'",
              "Q: 'Why is this claim recommended for approval?'",
              "Q: 'What evidence supports the diagnosis?'",
              "See structured answers with evidence citations",
              "Click citations to view source documents",
            ]}
          />

          <Step
            number={16}
            title="Make Final Decision (Overview Tab)"
            description="Return to Overview tab, scroll to 'Final Reviewer Decision' section:"
            details={[
              "Select 'Approve Claim'",
              "Enter mandatory reviewer comment",
              "Click 'Submit Decision'",
              "Confirm in modal dialog",
            ]}
          />

          <Step
            number={17}
            title="View Final State"
            description="Claim is now APPROVED. Review:"
            details={[
              "AI recommendation vs Human decision comparison",
              "Complete audit trail",
              "Hash-chained ledger entry",
              "Reviewer comment recorded",
            ]}
          />
        </div>
      </div>

      {/* Test Scenario 2 */}
      <div className="card p-6 border-2 border-amber-500">
        <div className="flex items-center gap-2 mb-4">
          <CheckCircle size={20} className="text-amber-600" />
          <h2 className="text-xl font-semibold text-slate-900">Bonus: Test Insufficient Evidence Scenario</h2>
        </div>

        <div className="space-y-4">
          <Step
            number={18}
            title="Open Claim CLM-2026-00144"
            description="Open this claim to see how the system handles insufficient evidence"
            link="/claims/CLM-2026-00144"
          />

          <Step
            number={19}
            title="Run Adjudication"
            description="Click 'Run Adjudication' - AI will flag NEEDS_REVIEW"
          />

          <Step
            number={20}
            title="Review Timeline Gap"
            description="Clinical History tab shows treatment gaps:"
            details={[
              "Mar 15 - Apr 20: 36 days documented",
              "Gap: Apr 20 - Jul 10 (81 days - no records)",
              "Jul 10 - Aug 5: 26 days documented",
              "Total: Only 62 days vs 180 required",
            ]}
          />

          <Step
            number={21}
            title="AI Assistant Explanation"
            description="Ask: 'Why is this claim flagged for human review?' See how AI distinguishes 'insufficient evidence' from 'requirement not satisfied'"
          />

          <Step
            number={22}
            title="Test Request Information Workflow"
            description="Use 'Request Information' decision to ask hospital for missing records"
          />
        </div>
      </div>

      {/* Quick Links */}
      <div className="card p-6 bg-slate-50">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Quick Access Links</h2>
        <div className="grid grid-cols-2 gap-3">
          <QuickLink href="/hospital/create-claim" label="Hospital: Create New Claim" />
          <QuickLink href="/review-queue" label="Insurance: Review Queue" />
          <QuickLink href="/claims/CLM-2026-00142" label="Demo Claim #1 (Approval)" />
          <QuickLink href="/claims/CLM-2026-00144" label="Demo Claim #2 (Insufficient)" />
          <QuickLink href="/claims" label="All Claims" />
          <QuickLink href="/" label="Dashboard" />
        </div>
      </div>

      {/* Key Features */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Key Features to Demonstrate</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <Feature title="AI-Powered Code Mapping" description="Automatic ICD-10, CPT, RxNorm normalization" />
          <Feature title="Interactive AI Chat" description="Ask questions, get evidence-backed answers" />
          <Feature title="Policy Matching" description="Automatic policy identification and requirement checking" />
          <Feature title="Evidence Citations" description="Every conclusion linked to source documents" />
          <Feature title="Temporal Analysis" description="Treatment timeline verification with exact day calculations" />
          <Feature title="Human Oversight" description="AI recommends, human decides with mandatory comments" />
          <Feature title="Complete Audit Trail" description="Hash-chained ledger with all actions recorded" />
          <Feature title="Insufficient Evidence Handling" description="Clear distinction between missing data and failed requirements" />
        </div>
      </div>
    </div>
  );
}

function Step({
  number,
  title,
  description,
  details,
  link,
}: {
  number: number;
  title: string;
  description: string;
  details?: string[];
  link?: string;
}) {
  return (
    <div className="flex gap-4">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
        {number}
      </div>
      <div className="flex-1">
        <h3 className="font-semibold text-slate-900 mb-1">{title}</h3>
        <p className="text-sm text-slate-600 mb-2">{description}</p>
        {details && (
          <ul className="space-y-1 text-sm text-slate-600">
            {details.map((detail, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="text-slate-400 mt-0.5">•</span>
                <span>{detail}</span>
              </li>
            ))}
          </ul>
        )}
        {link && (
          <Link href={link} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
            Go to page <ArrowRight size={14} />
          </Link>
        )}
      </div>
    </div>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 hover:border-blue-300 hover:bg-blue-50 transition-colors"
    >
      {label}
      <ArrowRight size={16} className="text-slate-400" />
    </Link>
  );
}

function Feature({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h4 className="font-semibold text-slate-900 mb-1">{title}</h4>
      <p className="text-slate-600">{description}</p>
    </div>
  );
}
