/**
 * Complete Demo Data for End-to-End Testing
 *
 * This provides a full workflow from hospital claim creation to insurance review
 */

export interface DemoPatient {
  patientId: string;
  patientName: string;
  dateOfBirth: string;
  gender: string;
  contactNumber: string;
  medicalHistory: string[];
}

export interface DemoHospitalClaim {
  // Form data
  patientName: string;
  patientId: string;
  dateOfBirth: string;
  gender: string;
  contactNumber: string;
  admissionDate: string;
  dischargeDate: string;
  chiefComplaint: string;
  diagnosisDescription: string;
  treatmentProvided: string;
  proceduresPerformed: string;
  medicationsGiven: string;
  hospitalName: string;
  hospitalId: string;
  department: string;
  attendingPhysician: string;
  roomType: string;
  facilitiesProvided: string;
  insuranceProvider: string;
  policyNumber: string;
  policyId: string;
  totalAmount: string;
  roomCharges: string;
  procedureCharges: string;
  medicationCharges: string;
  otherCharges: string;
}

export interface DemoInsuranceClaim {
  claim_id: string;
  patient_id: string;
  patient_name: string;
  hospital: string;
  payer_name: string;
  cpt_code: string;
  icd10_code: string;
  claim_amount: number;
  status: "PENDING" | "APPROVED" | "DENIED" | "REQUEST_INFO";
  submitted_date: string;
  ai_recommendation?: "APPROVE" | "DENY" | "NEEDS_REVIEW" | "REQUEST_INFO";

  // Extended fields for review
  policy_id: string;
  procedure_name: string;
  diagnosis_description: string;
  admission_date: string;
  discharge_date: string;
  attending_physician: string;
  department: string;
}

export interface DemoTimeline {
  date: string;
  type: "diagnosis" | "treatment" | "imaging" | "lab" | "medication" | "encounter";
  title: string;
  description: string;
  provider?: string;
  location?: string;
}

export interface DemoPolicyRequirement {
  id: string;
  name: string;
  status: "SATISFIED" | "NOT_SATISFIED" | "INSUFFICIENT_EVIDENCE" | "NEEDS_REVIEW";
  explanation: string;
  evidence: string[];
  policySection?: string;
}

export interface DemoAIResponse {
  status: "APPROVED" | "DENIED" | "NEEDS_REVIEW" | "REQUEST_INFO";
  matched_policy: {
    policy_id: string;
    title: string;
    payer_name: string;
    clinical_indications: string;
    step_therapy_required: boolean;
  };
  trajectory_result: {
    step_therapy_met: boolean;
    treatment_duration_days: number;
    earliest_treatment: string;
    latest_treatment: string;
  };
  cited_evidence: Array<{
    source_index: string;
    document_id: string;
    excerpt: string;
    relevance_score: number;
  }>;
  generated_letter: string;
  ledger_entry: {
    ledger_id: string;
    sequence_number: number;
    record_hash: string;
    prev_hash: string;
    timestamp: string;
  };
}

// Demo Scenario 1: Complete Approval Flow (Knee Replacement)
export const DEMO_SCENARIO_1 = {
  hospitalClaim: {
    patientName: "John Doe",
    patientId: "PAT-883910",
    dateOfBirth: "1965-03-15",
    gender: "Male",
    contactNumber: "+1 (555) 123-4567",
    admissionDate: "2026-08-10",
    dischargeDate: "2026-08-14",
    chiefComplaint: "Severe right knee pain limiting mobility and daily activities",
    diagnosisDescription: "Severe osteoarthritis of the right knee with Grade 4 chondromalacia, bone-on-bone contact, and significant joint space narrowing documented on imaging studies",
    treatmentProvided: "Total knee arthroplasty performed with cemented prosthesis implantation, postoperative pain management, physical therapy initiation, and comprehensive discharge planning",
    proceduresPerformed: "Total knee arthroplasty, right side (Primary procedure); Anesthesia services; Post-operative monitoring and care",
    medicationsGiven: "Metformin 500mg (continued from home), Losartan 50mg for hypertension, Oxycodone 5mg for post-operative pain management, Celecoxib 200mg for inflammation, Enoxaparin 40mg for DVT prophylaxis",
    hospitalName: "CityCare Hospital",
    hospitalId: "HOSP-001",
    department: "Orthopedics",
    attendingPhysician: "Dr. Sarah Mitchell, MD",
    roomType: "Private",
    facilitiesProvided: "Operating room with orthopedic equipment, Post-anesthesia care unit (PACU), Private recovery room, Physical therapy services, 24-hour nursing care, Medication administration",
    insuranceProvider: "ABC Health Insurance",
    policyNumber: "ABC-POL-883910-2026",
    policyId: "POL-KNEE-042",
    totalAmount: "48000",
    roomCharges: "8000",
    procedureCharges: "35000",
    medicationCharges: "3000",
    otherCharges: "2000",
  } as DemoHospitalClaim,

  insuranceClaim: {
    claim_id: "CLM-2026-00142",
    patient_id: "PAT-883910",
    patient_name: "John Doe",
    hospital: "CityCare Hospital",
    payer_name: "ABC Health Insurance",
    cpt_code: "27447",
    icd10_code: "M17.11",
    claim_amount: 48000,
    status: "PENDING" as const,
    submitted_date: "2026-08-15",
    ai_recommendation: "APPROVE" as const,
    policy_id: "POL-KNEE-042",
    procedure_name: "Total Knee Arthroplasty",
    diagnosis_description: "Unilateral primary osteoarthritis, right knee",
    admission_date: "2026-08-10",
    discharge_date: "2026-08-14",
    attending_physician: "Dr. Sarah Mitchell",
    department: "Orthopedics",
  },

  timeline: [
    {
      date: "2026-01-12",
      type: "diagnosis" as const,
      title: "Initial Diagnosis",
      description: "Osteoarthritis of right knee diagnosed during orthopedic consultation",
      provider: "Dr. Robert Chen, Orthopedics",
      location: "CityCare Hospital Orthopedic Clinic",
    },
    {
      date: "2026-02-03",
      type: "treatment" as const,
      title: "Physical Therapy - Initial Session",
      description: "Started conservative treatment regimen with focus on strengthening and range of motion",
      provider: "Sarah Johnson, PT, DPT",
      location: "CityCare Physical Therapy Center",
    },
    {
      date: "2026-03-08",
      type: "treatment" as const,
      title: "Physical Therapy - Follow-up",
      description: "Continued conservative treatment, minimal improvement noted",
      provider: "Sarah Johnson, PT, DPT",
      location: "CityCare Physical Therapy Center",
    },
    {
      date: "2026-04-12",
      type: "treatment" as const,
      title: "Physical Therapy - Session 3",
      description: "Ongoing conservative management, patient reports persistent pain",
      provider: "Sarah Johnson, PT, DPT",
      location: "CityCare Physical Therapy Center",
    },
    {
      date: "2026-05-20",
      type: "imaging" as const,
      title: "MRI Scan - Right Knee",
      description: "MRI demonstrates severe tricompartmental osteoarthritis with Grade 4 chondromalacia, extensive bone marrow edema, and large osteophytes. Significant joint space narrowing noted.",
      provider: "Dr. Michael Wong, Radiology",
      location: "CityCare Imaging Center",
    },
    {
      date: "2026-06-18",
      type: "treatment" as const,
      title: "Physical Therapy - Session 4",
      description: "Continued conservative treatment despite limited progress",
      provider: "Sarah Johnson, PT, DPT",
      location: "CityCare Physical Therapy Center",
    },
    {
      date: "2026-07-18",
      type: "treatment" as const,
      title: "Physical Therapy - Final Session",
      description: "Conservative treatment completed - 187 days total. Failed to achieve adequate symptom relief.",
      provider: "Sarah Johnson, PT, DPT",
      location: "CityCare Physical Therapy Center",
    },
    {
      date: "2026-08-03",
      type: "encounter" as const,
      title: "Orthopedic Consultation - Surgical Evaluation",
      description: "Surgeon evaluation confirms failure of conservative treatment. Patient is appropriate candidate for total knee arthroplasty.",
      provider: "Dr. Sarah Mitchell, Orthopedic Surgery",
      location: "CityCare Hospital",
    },
    {
      date: "2026-08-10",
      type: "encounter" as const,
      title: "Hospital Admission",
      description: "Patient admitted for total knee arthroplasty procedure",
      provider: "Dr. Sarah Mitchell, Orthopedic Surgery",
      location: "CityCare Hospital",
    },
    {
      date: "2026-08-10",
      type: "treatment" as const,
      title: "Total Knee Arthroplasty Performed",
      description: "Successful total knee arthroplasty performed. Cemented prosthesis implanted. No intraoperative complications.",
      provider: "Dr. Sarah Mitchell, Orthopedic Surgery",
      location: "CityCare Hospital Operating Room 3",
    },
    {
      date: "2026-08-14",
      type: "encounter" as const,
      title: "Hospital Discharge",
      description: "Patient discharged in stable condition with home physical therapy orders and pain management plan",
      provider: "Dr. Sarah Mitchell, Orthopedic Surgery",
      location: "CityCare Hospital",
    },
  ] as DemoTimeline[],

  policyRequirements: [
    {
      id: "req-1",
      name: "Diagnosis Requirement",
      status: "SATISFIED" as const,
      explanation: "Patient must have documented diagnosis of osteoarthritis or degenerative joint disease",
      evidence: [
        "Clinical examination documented 01/12/2026 by Dr. Robert Chen",
        "ICD-10 Code: M17.11 (Unilateral primary osteoarthritis, right knee)",
        "Physical examination findings consistent with severe osteoarthritis",
      ],
      policySection: "Section 2.1: Diagnostic Criteria",
    },
    {
      id: "req-2",
      name: "Conservative Treatment",
      status: "SATISFIED" as const,
      explanation: "Requires at least 6 months (180 days) of documented conservative treatment including physical therapy",
      evidence: [
        "Physical therapy documented from 02/03/2026 - 07/18/2026",
        "Duration: 187 days (exceeds 180-day requirement)",
        "5 documented physical therapy sessions with licensed therapist",
        "Conservative treatment notes demonstrate compliance and lack of improvement",
      ],
      policySection: "Section 3.2: Conservative Treatment Requirements",
    },
    {
      id: "req-3",
      name: "Treatment Duration",
      status: "SATISFIED" as const,
      explanation: "Conservative treatment must be documented for continuous period of at least 180 days",
      evidence: [
        "First physical therapy session: 02/03/2026",
        "Last physical therapy session: 07/18/2026",
        "Total documented duration: 187 days",
        "Calculation: 187 days > 180 days (requirement satisfied)",
      ],
      policySection: "Section 3.2: Conservative Treatment Requirements",
    },
    {
      id: "req-4",
      name: "Imaging Evidence",
      status: "SATISFIED" as const,
      explanation: "Imaging studies must document severity of degenerative changes",
      evidence: [
        "MRI performed 05/20/2026 by Dr. Michael Wong, Radiology",
        "Report documents: Grade 4 chondromalacia (severe cartilage damage)",
        "Extensive bone marrow edema pattern",
        "Significant joint space narrowing with bone-on-bone contact",
        "Large osteophyte formation",
      ],
      policySection: "Section 2.3: Imaging Requirements",
    },
    {
      id: "req-5",
      name: "Failed Conservative Treatment",
      status: "SATISFIED" as const,
      explanation: "Documentation must demonstrate that conservative treatment did not provide adequate symptom relief",
      evidence: [
        "PT notes document persistent pain throughout treatment course",
        "Patient reports minimal improvement in function",
        "Physical therapist notes: 'limited progress despite compliance'",
        "Orthopedic surgeon evaluation 08/03/2026: 'Failed conservative management'",
      ],
      policySection: "Section 3.4: Medical Necessity Criteria",
    },
    {
      id: "req-6",
      name: "Functional Limitations",
      status: "SATISFIED" as const,
      explanation: "Patient must demonstrate significant functional limitations",
      evidence: [
        "Chief complaint: 'Severe pain limiting mobility and daily activities'",
        "Patient unable to perform activities of daily living without significant pain",
        "Work capacity affected by knee pain and limited range of motion",
      ],
      policySection: "Section 2.4: Functional Status",
    },
  ] as DemoPolicyRequirement[],

  aiResponse: {
    status: "APPROVED" as const,
    matched_policy: {
      policy_id: "POL-KNEE-042",
      title: "Total Knee Arthroplasty Coverage Policy",
      payer_name: "ABC Health Insurance",
      clinical_indications: "Coverage for total knee arthroplasty when conservative treatment has failed and medical necessity is documented",
      step_therapy_required: true,
    },
    trajectory_result: {
      step_therapy_met: true,
      treatment_duration_days: 187,
      earliest_treatment: "2026-02-03",
      latest_treatment: "2026-07-18",
    },
    cited_evidence: [
      {
        source_index: "clinical-notes",
        document_id: "EV-18291",
        excerpt: "Physical therapy session initiated 02/03/2026. Patient demonstrates severe limitation in range of motion...",
        relevance_score: 0.95,
      },
      {
        source_index: "clinical-notes",
        document_id: "EV-19281",
        excerpt: "Physical therapy session 07/18/2026. Despite 187 days of conservative management, patient continues to experience severe pain...",
        relevance_score: 0.93,
      },
      {
        source_index: "imaging-reports",
        document_id: "EV-15822",
        excerpt: "MRI Right Knee (05/20/2026): Grade 4 chondromalacia with extensive bone marrow edema. Severe tricompartmental osteoarthritis...",
        relevance_score: 0.97,
      },
      {
        source_index: "medical-policies",
        document_id: "POL-KNEE-042-SEC-3.2",
        excerpt: "Conservative treatment including physical therapy for a minimum of 180 days is required prior to approval...",
        relevance_score: 0.98,
      },
    ],
    generated_letter: `CLAIM ADJUDICATION DECISION

Claim ID: CLM-2026-00142
Patient: John Doe (PAT-883910)
Procedure: Total Knee Arthroplasty (CPT 27447)
Policy: POL-KNEE-042
Decision Date: ${new Date().toLocaleDateString()}

DECISION: APPROVED

This claim has been reviewed and approved for payment. All policy requirements have been satisfied:

✓ Diagnosis Requirement: Documented severe osteoarthritis (ICD-10: M17.11)
✓ Conservative Treatment: 187 days of physical therapy documented (exceeds 180-day requirement)
✓ Imaging Evidence: MRI demonstrates Grade 4 chondromalacia with severe degenerative changes
✓ Failed Conservative Treatment: Documentation supports lack of improvement with conservative management
✓ Medical Necessity: Clinical documentation supports medical necessity for surgical intervention

APPROVED AMOUNT: $48,000.00

Payment will be processed according to policy terms and provider contract rates.

This decision is based on evidence-backed review of clinical documentation, policy requirements, and medical necessity criteria. All cited evidence has been verified and is available in the claim record.`,
    ledger_entry: {
      ledger_id: "LEDGER-2026-001",
      sequence_number: 142,
      record_hash: "a7f3e9c2b5d8e1f4a6b9c3d7e2f5a8b1",
      prev_hash: "b8f4e0d3c6e9f2a5b7c0d4e8f3a6b9c2",
      timestamp: new Date().toISOString(),
    },
  } as DemoAIResponse,
};

// Demo Scenario 2: Insufficient Evidence (Treatment Gap)
export const DEMO_SCENARIO_2 = {
  insuranceClaim: {
    claim_id: "CLM-2026-00144",
    patient_id: "PAT-762394",
    patient_name: "Michael Brown",
    hospital: "Regional Medical Center",
    payer_name: "Aetna",
    cpt_code: "27447",
    icd10_code: "M17.12",
    claim_amount: 45000,
    status: "PENDING" as const,
    submitted_date: "2026-08-18",
    ai_recommendation: "NEEDS_REVIEW" as const,
    policy_id: "POL-KNEE-042",
    procedure_name: "Total Knee Arthroplasty",
    diagnosis_description: "Unilateral primary osteoarthritis, left knee",
    admission_date: "2026-08-15",
    discharge_date: "2026-08-18",
    attending_physician: "Dr. James Wilson",
    department: "Orthopedics",
  },

  timeline: [
    {
      date: "2026-03-15",
      type: "diagnosis" as const,
      title: "Initial Diagnosis",
      description: "Osteoarthritis of left knee diagnosed",
      provider: "Dr. James Wilson",
      location: "Regional Medical Center",
    },
    {
      date: "2026-03-15",
      type: "treatment" as const,
      title: "Physical Therapy - Session 1",
      description: "Initial physical therapy evaluation and treatment",
      provider: "Physical Therapy Department",
      location: "Regional Medical Center",
    },
    {
      date: "2026-04-20",
      type: "treatment" as const,
      title: "Physical Therapy - Session 2",
      description: "Follow-up physical therapy - 36 days from start",
      provider: "Physical Therapy Department",
      location: "Regional Medical Center",
    },
    // GAP IN RECORDS: Apr 20 - Jul 10 (81 days)
    {
      date: "2026-07-10",
      type: "treatment" as const,
      title: "Physical Therapy - Session 3",
      description: "Physical therapy resumed after gap in documentation",
      provider: "Physical Therapy Department",
      location: "Regional Medical Center",
    },
    {
      date: "2026-08-05",
      type: "treatment" as const,
      title: "Physical Therapy - Session 4",
      description: "Final physical therapy session - 26 days in this period",
      provider: "Physical Therapy Department",
      location: "Regional Medical Center",
    },
  ] as DemoTimeline[],

  policyRequirements: [
    {
      id: "req-1",
      name: "Diagnosis Requirement",
      status: "SATISFIED" as const,
      explanation: "Patient must have documented diagnosis of osteoarthritis",
      evidence: [
        "Clinical examination — 03/15/2026",
        "ICD-10: M17.12",
      ],
    },
    {
      id: "req-2",
      name: "Conservative Treatment",
      status: "INSUFFICIENT_EVIDENCE" as const,
      explanation: "Requires at least 6 months (180 days) of conservative treatment",
      evidence: [
        "Physical therapy: 03/15 - 04/20/2026 (36 days documented)",
        "Gap in records: 04/20 - 07/10/2026 (81 days - no documentation)",
        "Physical therapy: 07/10 - 08/05/2026 (26 days documented)",
        "Total documented: 62 days (insufficient - requires 180 days)",
      ],
    },
    {
      id: "req-3",
      name: "Treatment Duration",
      status: "INSUFFICIENT_EVIDENCE" as const,
      explanation: "Cannot establish continuous 6-month treatment period",
      evidence: [
        "Available records do not establish continuous 180-day treatment",
        "Gap between 04/20 and 07/10 (81 days) is not documented",
        "Cannot verify if treatment occurred during gap period",
      ],
    },
  ] as DemoPolicyRequirement[],
};

// Export all scenarios
export const ALL_DEMO_SCENARIOS = {
  scenario1: DEMO_SCENARIO_1,
  scenario2: DEMO_SCENARIO_2,
};

// Demo data manager for localStorage
export class DemoDataManager {
  private static STORAGE_KEY = "mediaudit_demo_claims";

  static saveClaim(claim: DemoInsuranceClaim) {
    const claims = this.getAllClaims();
    const existingIndex = claims.findIndex(c => c.claim_id === claim.claim_id);

    if (existingIndex >= 0) {
      claims[existingIndex] = claim;
    } else {
      claims.push(claim);
    }

    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(claims));
  }

  static getAllClaims(): DemoInsuranceClaim[] {
    if (typeof window === "undefined") return [];

    const stored = localStorage.getItem(this.STORAGE_KEY);
    if (!stored) {
      // Initialize with demo scenarios - set to PENDING for insurance review
      const initialClaims = [
        { ...DEMO_SCENARIO_1.insuranceClaim, status: "PENDING" as const },
        { ...DEMO_SCENARIO_2.insuranceClaim, status: "PENDING" as const },
        // Additional demo claims for insurance testing
        {
          claim_id: "CLM-2026-00201",
          patient_id: "PAT-445623",
          patient_name: "Sarah Johnson",
          hospital: "Metro General Hospital",
          payer_name: "HealthFirst Insurance",
          cpt_code: "99285",
          icd10_code: "I21.09",
          claim_amount: 12500,
          status: "PENDING" as const,
          submitted_date: "2026-09-10",
          ai_recommendation: "APPROVE" as const,
          policy_id: "POL-EMRG-089",
          procedure_name: "Emergency Department Visit - High Complexity",
          diagnosis_description: "Acute myocardial infarction",
          admission_date: "2026-09-08",
          discharge_date: "2026-09-09",
          attending_physician: "Dr. James Wilson",
          department: "Emergency Medicine",
        },
        {
          claim_id: "CLM-2026-00198",
          patient_id: "PAT-772341",
          patient_name: "Robert Martinez",
          hospital: "St. Mary's Medical Center",
          payer_name: "United Care Insurance",
          cpt_code: "43239",
          icd10_code: "K92.2",
          claim_amount: 8750,
          status: "PENDING" as const,
          submitted_date: "2026-09-12",
          ai_recommendation: "REQUEST_INFO" as const,
          policy_id: "POL-ENDO-034",
          procedure_name: "Upper GI Endoscopy with Biopsy",
          diagnosis_description: "Gastrointestinal hemorrhage, unspecified",
          admission_date: "2026-09-11",
          discharge_date: "2026-09-11",
          attending_physician: "Dr. Lisa Chen",
          department: "Gastroenterology",
        },
        {
          claim_id: "CLM-2026-00175",
          patient_id: "PAT-889012",
          patient_name: "Emily Davis",
          hospital: "Riverside Medical Center",
          payer_name: "BlueCross BlueShield",
          cpt_code: "29826",
          icd10_code: "M75.120",
          claim_amount: 22000,
          status: "PENDING" as const,
          submitted_date: "2026-09-05",
          ai_recommendation: "APPROVE" as const,
          policy_id: "POL-ORTH-067",
          procedure_name: "Arthroscopic Rotator Cuff Repair",
          diagnosis_description: "Complete rotator cuff tear, right shoulder",
          admission_date: "2026-09-03",
          discharge_date: "2026-09-04",
          attending_physician: "Dr. Michael Torres",
          department: "Orthopedic Surgery",
        },
        {
          claim_id: "CLM-2026-00156",
          patient_id: "PAT-334567",
          patient_name: "David Thompson",
          hospital: "Valley View Hospital",
          payer_name: "Aetna Insurance",
          cpt_code: "00630",
          icd10_code: "C61",
          claim_amount: 45000,
          status: "PENDING" as const,
          submitted_date: "2026-08-28",
          ai_recommendation: "DENY" as const,
          policy_id: "POL-SURG-123",
          procedure_name: "Radical Prostatectomy",
          diagnosis_description: "Malignant neoplasm of prostate",
          admission_date: "2026-08-25",
          discharge_date: "2026-08-27",
          attending_physician: "Dr. Patricia Anderson",
          department: "Urology",
        },
      ];
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(initialClaims));
      return initialClaims;
    }

    return JSON.parse(stored);
  }

  static getClaim(claimId: string): DemoInsuranceClaim | null {
    const claims = this.getAllClaims();
    return claims.find(c => c.claim_id === claimId) || null;
  }

  static updateClaimStatus(claimId: string, status: DemoInsuranceClaim["status"], aiRecommendation?: string) {
    const claims = this.getAllClaims();
    const claim = claims.find(c => c.claim_id === claimId);

    if (claim) {
      claim.status = status;
      if (aiRecommendation) {
        claim.ai_recommendation = aiRecommendation as any;
      }
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(claims));
    }
  }

  static getTimeline(patientId: string): DemoTimeline[] {
    // Return appropriate timeline based on patient
    if (patientId === "PAT-883910") {
      return DEMO_SCENARIO_1.timeline;
    } else if (patientId === "PAT-762394") {
      return DEMO_SCENARIO_2.timeline;
    }
    return [];
  }

  static getPolicyRequirements(claimId: string): DemoPolicyRequirement[] {
    if (claimId === "CLM-2026-00142") {
      return DEMO_SCENARIO_1.policyRequirements;
    } else if (claimId === "CLM-2026-00144") {
      return DEMO_SCENARIO_2.policyRequirements;
    }
    return [];
  }

  static getAIResponse(claimId: string): DemoAIResponse | null {
    if (claimId === "CLM-2026-00142") {
      return DEMO_SCENARIO_1.aiResponse;
    }
    return null;
  }

  static initializeDemoData() {
    this.getAllClaims(); // This will initialize if not present
  }
}
