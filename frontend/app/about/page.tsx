"use client";

import {
  FileSearch,
  ShieldCheck,
  MessagesSquare,
  Link2,
  Upload,
  Sparkles,
  ClipboardCheck,
  History as HistoryIcon,
  Compass,
} from "lucide-react";
import Button from "../components/ui/Button";
import { useRole } from "../contexts/RoleContext";
import { resetTour } from "../components/ProductTour";

const CAPABILITIES = [
  {
    icon: FileSearch,
    title: "Reads the actual documents",
    description:
      "Referral letters, bills, and clinical notes are extracted automatically -- every field a claim uses traces back to a real page and passage, not a guess.",
  },
  {
    icon: Sparkles,
    title: "AI-assisted, not AI-decided",
    description:
      "The assistant checks payer policy, patient history, and drug interactions in real data -- but the final approve/deny call is computed by fixed rules, never left to a model's word alone.",
  },
  {
    icon: Link2,
    title: "Every claim, cited",
    description:
      "Click any finding and see exactly which policy clause, encounter, or interaction record it came from -- \"claims you can cite, not just trust.\"",
  },
  {
    icon: ShieldCheck,
    title: "Tamper-evident audit trail",
    description:
      "Every decision is chained into a hash-linked ledger. If any past entry were altered, the chain would break and show it.",
  },
  {
    icon: MessagesSquare,
    title: "Ask it anything about a claim",
    description:
      "The claim chat answers reviewer questions -- \"was step therapy met?\", \"why was this denied?\" -- by looking the facts up live, with sources shown.",
  },
  {
    icon: ClipboardCheck,
    title: "Built for both sides",
    description:
      "Hospitals submit and track claims; reviewers adjudicate them -- same underlying evidence, two workflows shaped around what each side actually needs to do.",
  },
];

const HOW_IT_WORKS = [
  { icon: Upload, title: "Submit", detail: "A hospital uploads claim documents -- referral letters, bills, imaging reports." },
  { icon: FileSearch, title: "Extract & verify", detail: "Text is pulled from every document and checked against the claim's codes." },
  { icon: Compass, title: "Review", detail: "Policy match, treatment history, and interaction checks run against real data, with reasoning shown live." },
  { icon: HistoryIcon, title: "Decide & record", detail: "A reviewer makes the final call; the decision and its evidence are sealed into the audit ledger." },
];

export default function AboutPage() {
  const { role } = useRole();

  return (
    <div className="mx-auto max-w-4xl animate-slide-up space-y-8">
      {/* Hero */}
      <div className="card overflow-hidden">
        <div className="bg-gradient-to-br from-blue-600 to-navy-900 px-8 py-10 text-white">
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 text-lg font-bold">
            M
          </div>
          <h1 className="text-2xl font-semibold">MediAudit-X</h1>
          <p className="mt-2 max-w-xl text-sm text-blue-100">
            Claims you can cite, not just trust. A clinical claims platform where
            every adjudication decision is grounded in real evidence -- policy
            text, patient history, and drug-safety data -- and cited back to its
            source, rather than left to AI inference alone.
          </p>
        </div>
        <div className="p-6 text-sm text-slate-600">
          {role === "hospital" ? (
            <p>
              As a <strong className="text-slate-800">hospital</strong>, you use MediAudit-X to submit
              claims with supporting documents and track exactly where each one
              stands -- with a real reason attached the moment a decision is made,
              not just a status flip.
            </p>
          ) : (
            <p>
              As an <strong className="text-slate-800">insurance reviewer</strong>, you use MediAudit-X to
              adjudicate claims against real payer policy, a patient's actual
              treatment history, and known drug interactions -- with every
              finding traceable to its source, and a tamper-evident record of
              every call you make.
            </p>
          )}
        </div>
      </div>

      {/* Capabilities */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">What it does</h2>
        <div className="grid grid-cols-2 gap-4">
          {CAPABILITIES.map(({ icon: Icon, title, description }, i) => (
            <div
              key={title}
              className="card animate-slide-up p-5"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50">
                <Icon size={18} className="text-blue-600" />
              </div>
              <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
              <p className="mt-1 text-sm text-slate-500">{description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">How it works</h2>
        <div className="card p-6">
          <div className="grid grid-cols-4 gap-4">
            {HOW_IT_WORKS.map(({ icon: Icon, title, detail }, i) => (
              <div key={title} className="relative">
                {i < HOW_IT_WORKS.length - 1 && (
                  <div className="absolute right-0 top-5 hidden h-px w-full translate-x-1/2 bg-slate-200 sm:block" />
                )}
                <div className="relative flex flex-col items-center text-center">
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white">
                    <Icon size={17} />
                  </div>
                  <div className="text-sm font-semibold text-slate-800">{title}</div>
                  <p className="mt-1 text-xs text-slate-500">{detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Replay the tour */}
      <div className="card flex items-center justify-between p-5">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">New around here?</h3>
          <p className="mt-0.5 text-sm text-slate-500">Replay the guided tour of the sidebar and key pages.</p>
        </div>
        <Button
          variant="outline"
          icon={<Compass size={15} />}
          onClick={() => {
            if (role) {
              resetTour(role);
              window.location.reload();
            }
          }}
        >
          Replay tour
        </Button>
      </div>
    </div>
  );
}
