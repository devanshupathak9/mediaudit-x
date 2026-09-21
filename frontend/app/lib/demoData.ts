/**
 * Demo data for MediAudit-X hackathon demonstration
 *
 * These scenarios showcase the complete workflow:
 * 1. CLM-2026-00142: Approval scenario - all requirements satisfied
 * 2. CLM-2026-00143: Human review required - conflicting evidence
 * 3. CLM-2026-00144: Insufficient evidence - incomplete treatment history
 * 4. CLM-2026-00145: Denial recommendation - policy criterion not satisfied
 */

export interface DemoClaim {
  claim_id: string;
  patient_id: string;
  patient_name: string;
  hospital: string;
  procedure: string;
  cpt_code: string;
  icd10_code: string;
  payer_name: string;
  policy_id: string;
  claim_amount: number;
  status: string;
  submitted_date: string;
  ai_recommendation?: string;
  scenario_type: "approval" | "human_review" | "insufficient_evidence" | "denial";
}

export interface DemoTimeline {
  date: string;
  type: "diagnosis" | "treatment" | "imaging" | "lab" | "medication" | "encounter";
  title: string;
  description: string;
}

export interface DemoPolicyRequirement {
  id: string;
  name: string;
  status: "SATISFIED" | "NOT_SATISFIED" | "INSUFFICIENT_EVIDENCE" | "NEEDS_REVIEW";
  explanation: string;
  evidence: string[];
}

export const DEMO_CLAIMS: DemoClaim[] = [
  {
    claim_id: "CLM-2026-00142",
    patient_id: "PAT-883910",
    patient_name: "John Doe",
    hospital: "CityCare Hospital",
    procedure: "Total Knee Replacement",
    cpt_code: "27447",
    icd10_code: "M17.11",
    payer_name: "ABC Health Insurance",
    policy_id: "POL-KNEE-042",
    claim_amount: 48000,
    status: "PENDING",
    submitted_date: "2026-09-18",
    ai_recommendation: "APPROVE",
    scenario_type: "approval",
  },
  {
    claim_id: "CLM-2026-00143",
    patient_id: "PAT-445821",
    patient_name: "Sarah Smith",
    hospital: "MetroHealth Medical Center",
    procedure: "Spinal Fusion Surgery",
    cpt_code: "22612",
    icd10_code: "M51.26",
    payer_name: "United Healthcare",
    policy_id: "POL-SPINE-089",
    claim_amount: 92000,
    status: "PENDING",
    ai_recommendation: "NEEDS_REVIEW",
    scenario_type: "human_review",
  },
  {
    claim_id: "CLM-2026-00144",
    patient_id: "PAT-762394",
    patient_name: "Michael Brown",
    hospital: "Regional Medical Center",
    procedure: "Total Knee Replacement",
    cpt_code: "27447",
    icd10_code: "M17.12",
    payer_name: "Aetna",
    policy_id: "POL-KNEE-042",
    claim_amount: 45000,
    status: "PENDING",
    ai_recommendation: "NEEDS_REVIEW",
    scenario_type: "insufficient_evidence",
  },
  {
    claim_id: "CLM-2026-00145",
    patient_id: "PAT-238905",
    patient_name: "Priya Sharma",
    hospital: "Community Hospital",
    procedure: "Cosmetic Rhinoplasty",
    cpt_code: "30400",
    icd10_code: "J34.89",
    payer_name: "Cigna",
    policy_id: "POL-COSM-001",
    claim_amount: 12000,
    status: "PENDING",
    ai_recommendation: "DENY",
    scenario_type: "denial",
  },
];

// Timeline for CLM-2026-00142 (approval scenario)
export const DEMO_TIMELINE_APPROVAL: DemoTimeline[] = [
  {
    date: "2026-01-12",
    type: "diagnosis",
    title: "Initial Diagnosis",
    description: "Osteoarthritis of right knee diagnosed",
  },
  {
    date: "2026-02-03",
    type: "treatment",
    title: "Physical Therapy - Session 1",
    description: "Started conservative treatment regimen",
  },
  {
    date: "2026-03-08",
    type: "treatment",
    title: "Physical Therapy - Session 2",
    description: "Continued conservative treatment",
  },
  {
    date: "2026-04-12",
    type: "treatment",
    title: "Physical Therapy - Session 3",
    description: "Ongoing conservative management",
  },
  {
    date: "2026-05-20",
    type: "imaging",
    title: "MRI Scan",
    description: "MRI shows severe degeneration and cartilage loss",
  },
  {
    date: "2026-06-18",
    type: "treatment",
    title: "Physical Therapy - Session 4",
    description: "Continued conservative treatment",
  },
  {
    date: "2026-07-18",
    type: "treatment",
    title: "Physical Therapy - Session 5",
    description: "Final conservative treatment session - 187 days total",
  },
  {
    date: "2026-08-03",
    type: "encounter",
    title: "Orthopedic Consultation",
    description: "Surgeon recommends total knee replacement",
  },
  {
    date: "2026-08-10",
    type: "encounter",
    title: "Surgery Scheduled",
    description: "Total knee replacement procedure requested",
  },
];

// Policy requirements for CLM-2026-00142 (approval scenario)
export const DEMO_POLICY_REQUIREMENTS_APPROVAL: DemoPolicyRequirement[] = [
  {
    id: "req-1",
    name: "Diagnosis Requirement",
    status: "SATISFIED",
    explanation: "Patient must have documented diagnosis of osteoarthritis",
    evidence: ["Clinical examination — Jan 12, 2026", "ICD-10: M17.11"],
  },
  {
    id: "req-2",
    name: "Conservative Treatment",
    status: "SATISFIED",
    explanation: "Requires at least 6 months (180 days) of conservative treatment",
    evidence: [
      "Physical therapy documented from Jan 12 - Jul 18, 2026",
      "Duration: 187 days",
      "5 documented sessions",
    ],
  },
  {
    id: "req-3",
    name: "Treatment Duration",
    status: "SATISFIED",
    explanation: "Conservative treatment must be documented for required period",
    evidence: ["First PT: Jan 12, 2026", "Last PT: Jul 18, 2026", "Total: 187 days (exceeds 180-day requirement)"],
  },
  {
    id: "req-4",
    name: "Imaging Evidence",
    status: "SATISFIED",
    explanation: "Imaging must document severity of condition",
    evidence: ["MRI report — May 20, 2026", "Shows severe degeneration and cartilage loss"],
  },
];

// Policy requirements for CLM-2026-00144 (insufficient evidence scenario)
export const DEMO_POLICY_REQUIREMENTS_INSUFFICIENT: DemoPolicyRequirement[] = [
  {
    id: "req-1",
    name: "Diagnosis Requirement",
    status: "SATISFIED",
    explanation: "Patient must have documented diagnosis of osteoarthritis",
    evidence: ["Clinical examination — Mar 15, 2026", "ICD-10: M17.12"],
  },
  {
    id: "req-2",
    name: "Conservative Treatment",
    status: "INSUFFICIENT_EVIDENCE",
    explanation: "Requires at least 6 months (180 days) of conservative treatment",
    evidence: [
      "Physical therapy: Mar 15 - Apr 20, 2026 (36 days)",
      "Gap in records",
      "Physical therapy: Jul 10 - Aug 5, 2026 (26 days)",
      "Total documented: 62 days (insufficient)",
    ],
  },
  {
    id: "req-3",
    name: "Treatment Duration",
    status: "INSUFFICIENT_EVIDENCE",
    explanation: "Cannot establish continuous 6-month treatment period",
    evidence: [
      "Available records do not establish continuous 180-day treatment",
      "Gap between Apr 20 and Jul 10 not documented",
    ],
  },
  {
    id: "req-4",
    name: "Imaging Evidence",
    status: "SATISFIED",
    explanation: "Imaging must document severity of condition",
    evidence: ["MRI report — Jun 22, 2026", "Shows moderate to severe degeneration"],
  },
];

export const DEMO_CHAT_MESSAGES = {
  approval: [
    {
      question: "Was the conservative treatment requirement satisfied?",
      answer: `Yes. The available clinical records support the requirement.

**Why:**
The applicable policy requires at least 180 days of conservative treatment.

The patient timeline contains:
• Jan 12 — Physical therapy started
• Jul 18 — Physical therapy documented

Observed interval: 187 days

**Conclusion:**
Requirement: SATISFIED`,
      citations: [
        { id: "EV-18291", type: "clinical_note", description: "PT note — Jan 12, 2026" },
        { id: "EV-19281", type: "clinical_note", description: "PT note — Jul 18, 2026" },
        { id: "POL-042-4.2", type: "policy", description: "Policy section 4.2" },
      ],
    },
  ],
  insufficient: [
    {
      question: "Why is this claim flagged for human review?",
      answer: `The claim requires human review because the available records do not establish continuous 6-month conservative treatment.

**Issue:**
The policy requires at least 180 days of documented conservative treatment.

**Available evidence:**
• Mar 15 - Apr 20: 36 days documented
• Apr 20 - Jul 10: Gap in records (81 days)
• Jul 10 - Aug 5: 26 days documented

**Total documented:** 62 days

**Conclusion:**
Insufficient evidence to establish the requirement. The gap period is not documented, so we cannot determine if treatment continued during that time.`,
      citations: [
        { id: "EV-22819", type: "clinical_note", description: "PT records — Mar-Apr 2026" },
        { id: "EV-24102", type: "clinical_note", description: "PT records — Jul-Aug 2026" },
      ],
    },
  ],
};
