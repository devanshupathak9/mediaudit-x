"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, FileText, CheckCircle, Upload, User, Hospital, DollarSign, X, Paperclip } from "lucide-react";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import LoadingSpinner from "../../components/ui/LoadingSpinner";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// Mirrors ALLOWED_EXTENSIONS / DOC_TYPES in backend app/pipeline/ingestion/models.py.
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff";
const DOC_TYPES = [
  ["supporting_document", "Supporting document"],
  ["referral_letter", "Referral letter"],
  ["op_note", "Operative note"],
  ["discharge_summary", "Discharge summary"],
  ["lab_report", "Lab report"],
  ["prescription", "Prescription"],
  ["imaging_report", "Imaging report"],
  ["other", "Other"],
] as const;

type Rejected = { filename: string; code: string; message: string };
type SubmitResult = {
  claim: { claim_id: string; status: string };
  accepted: { doc_id: string; original_filename: string; source_uri: string }[];
  rejected: Rejected[];
};

type Step = "details" | "review" | "submitting" | "success";

interface SimpleClaimFormData {
  // Stored on the claim record itself (claim-files)
  patientId: string;
  claimId: string;
  claimType: string;
  docType: string;
  hospitalName: string;

  // Patient Basic Info
  patientName: string;
  patientAge: string;
  patientGender: string;
  patientContact: string;

  // Clinical Information (Plain Language)
  chiefComplaint: string;
  problemDescription: string;
  symptomsDescription: string;
  howLongProblem: string;

  // Treatment Information (Plain Language)
  treatmentDescription: string;
  proceduresDescription: string;
  medicationsGiven: string;
  diagnosisInWords: string;

  // Admission Details
  admissionDate: string;
  dischargeDate: string;
  lengthOfStay: string;

  // Facilities & Services Provided (General)
  roomCategory: string;
  specialFacilities: string;
  servicesProvided: string;

  // Hospital Information
  departmentName: string;
  attendingDoctor: string;

  // Insurance & Billing (General)
  insuranceCompany: string;
  policyNumber: string;
  estimatedTotalCost: string;
}

const EMPTY_FORM: SimpleClaimFormData = {
  patientId: "",
  claimId: "",
  claimType: "professional",
  docType: "supporting_document",
  hospitalName: "",
  patientName: "",
  patientAge: "",
  patientGender: "",
  patientContact: "",
  chiefComplaint: "",
  problemDescription: "",
  symptomsDescription: "",
  howLongProblem: "",
  treatmentDescription: "",
  proceduresDescription: "",
  medicationsGiven: "",
  diagnosisInWords: "",
  admissionDate: "",
  dischargeDate: "",
  lengthOfStay: "",
  roomCategory: "",
  specialFacilities: "",
  servicesProvided: "",
  departmentName: "",
  attendingDoctor: "",
  insuranceCompany: "",
  policyNumber: "",
  estimatedTotalCost: "",
};

export default function CreateClaimPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("details");
  const [formData, setFormData] = useState<SimpleClaimFormData>(EMPTY_FORM);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [rejectedFiles, setRejectedFiles] = useState<Rejected[]>([]);

  const updateForm = <K extends keyof SimpleClaimFormData>(key: K, value: SimpleClaimFormData[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  // No codes, policy match or billing split are produced here: nothing on
  // this page has real data to derive them from. Codes come later from the
  // uploaded documents (OCR -> claim draft -> coder review), and the policy
  // match from adjudication against the medical-policies index.
  const handleReview = () => {
    setSubmitError(null);
    setStep("review");
  };

  // Creates the claim (DRAFT) with its details and any documents via POST /claims/intake.
  const handleApproveAndSubmit = async () => {
    setStep("submitting");
    setSubmitError(null);
    setRejectedFiles([]);

    const f = formData;
    const details = {
      patient: { name: f.patientName, age: f.patientAge, gender: f.patientGender, contact: f.patientContact },
      clinical: {
        chief_complaint: f.chiefComplaint,
        problem_description: f.problemDescription,
        symptoms: f.symptomsDescription,
        duration: f.howLongProblem,
        diagnosis_in_words: f.diagnosisInWords,
        treatment: f.treatmentDescription,
        procedures: f.proceduresDescription,
        medications: f.medicationsGiven,
      },
      admission: { admission_date: f.admissionDate, discharge_date: f.dischargeDate, length_of_stay: f.lengthOfStay },
      services: {
        room_category: f.roomCategory,
        special_facilities: f.specialFacilities,
        services_provided: f.servicesProvided,
      },
      hospital: { name: f.hospitalName, department: f.departmentName, attending_doctor: f.attendingDoctor },
      insurance: { company: f.insuranceCompany, policy_number: f.policyNumber },
      estimated_total_cost: f.estimatedTotalCost || null,
    };

    const fd = new FormData();
    if (f.patientId.trim()) fd.append("patient_id", f.patientId.trim());
    if (f.insuranceCompany.trim()) fd.append("payer_name", f.insuranceCompany.trim());
    fd.append("claim_type", f.claimType);
    fd.append("doc_type", f.docType);
    if (f.claimId.trim()) fd.append("claim_id", f.claimId.trim());
    if (f.hospitalName.trim()) fd.append("submitted_by", f.hospitalName.trim());
    fd.append("details", JSON.stringify(details));
    for (const file of uploadedFiles) fd.append("files", file);

    try {
      let res: Response;
      try {
        res = await fetch(`${API_BASE_URL}/claims/intake`, { method: "POST", body: fd });
      } catch {
        throw new Error(`Could not reach the API at ${API_BASE_URL}. Is the backend running?`);
      }
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setRejectedFiles(body.rejected || []);
        throw new Error(typeof body.detail === "string" ? body.detail : `Submit failed (${res.status})`);
      }
      setSubmitResult(body as SubmitResult);
      setRejectedFiles(body.rejected || []);
      setStep("success");
    } catch (err: any) {
      setSubmitError(err.message || "Something went wrong.");
      setStep("review");
    }
  };

  const handleEditAndRegenerate = () => {
    setStep("details");
  };

  if (step === "success") {
    return (
      <div className="max-w-2xl mx-auto space-y-5">
        <div className="card p-8 text-center">
          <div className="flex justify-center mb-4">
            <div className="h-16 w-16 rounded-full bg-emerald-100 flex items-center justify-center">
              <CheckCircle size={32} className="text-emerald-600" />
            </div>
          </div>
          <h1 className="text-2xl font-semibold text-slate-900 mb-2">Claim Created</h1>
          <p className="text-slate-600 mb-6">
            Saved as <span className="font-medium">{submitResult?.claim.status ?? "DRAFT"}</span> with its details and
            documents. Medical codes are extracted automatically from the uploaded documents and the form details you entered.
          </p>

          <div className="bg-slate-50 rounded-lg p-4 mb-6 text-left">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500">Claim ID:</span>
                <div className="font-semibold text-slate-900">{submitResult?.claim.claim_id}</div>
              </div>
              <div>
                <span className="text-slate-500">Patient:</span>
                <div className="font-semibold text-slate-900">{formData.patientName}</div>
              </div>
              <div>
                <span className="text-slate-500">Insurance:</span>
                <div className="font-semibold text-slate-900">{formData.insuranceCompany}</div>
              </div>
              <div>
                <span className="text-slate-500">Amount:</span>
                <div className="font-semibold text-slate-900">{formatAmount(formData.estimatedTotalCost)}</div>
              </div>
            </div>
          </div>

          {submitResult && submitResult.accepted.length > 0 && (
            <div className="mb-6 text-left text-sm">
              <div className="mb-1 font-medium text-slate-700">
                {submitResult.accepted.length} document{submitResult.accepted.length === 1 ? "" : "s"} stored:
              </div>
              <ul className="space-y-1">
                {submitResult.accepted.map((d) => (
                  <li key={d.doc_id} className="rounded bg-slate-50 px-3 py-1.5 text-slate-600">
                    {d.original_filename} <span className="text-slate-400">· {d.doc_id}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {rejectedFiles.length > 0 && <RejectedNotice rejected={rejectedFiles} />}

          <div className="flex gap-3 justify-center">
            <Button variant="outline" onClick={() => router.push("/claims")}>
              View All Claims
            </Button>
            {submitResult && (
              <Button variant="outline" onClick={() => router.push(`/hospital/claims/${submitResult.claim.claim_id}`)}>
                Open Claim {submitResult.claim.claim_id}
              </Button>
            )}
            <Button variant="primary" onClick={() => {
              setStep("details");
              setFormData(EMPTY_FORM);
              setUploadedFiles([]);
              setSubmitResult(null);
              setRejectedFiles([]);
            }}>
              Create Another Claim
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <Link href="/claims" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-2">
          <ArrowLeft size={14} /> Back to Claims
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">Create Insurance Claim</h1>
        <p className="mt-1 text-sm text-slate-500">
          Describe the patient's treatment and attach the supporting documents. Medical codes are generated from the
          uploaded documents after submission and checked by a coder.
        </p>
      </div>

      {/* Progress Steps */}
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <StepIndicator
            number={1}
            label="Describe Treatment"
            active={step === "details"}
            completed={step !== "details"}
          />
          <div className="flex-1 h-0.5 bg-slate-200 mx-4" />
          <StepIndicator
            number={2}
            label="Review"
            active={step === "review"}
            completed={step === "submitting" || step === "success"}
          />
          <div className="flex-1 h-0.5 bg-slate-200 mx-4" />
          <StepIndicator
            number={3}
            label="Submit"
            active={step === "submitting"}
            completed={step === "success"}
          />
        </div>
      </div>

      {/* Step 1: Enter Simple Details */}
      {step === "details" && (
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); handleReview(); }}>
          <Alert type="info" title="No Technical Knowledge Required">
            Just describe the treatment in your own words. The AI will handle all medical codes, technical terms, and insurance documentation.
          </Alert>

          {/* Patient Information */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <User size={20} className="text-blue-600" />
              <h2 className="text-lg font-semibold text-slate-900">Patient Information</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Patient ID">
                <input
                  value={formData.patientId}
                  onChange={(e) => updateForm("patientId", e.target.value)}
                  placeholder="e.g., PAT-883910"
                  className="input"
                />
              </FormField>
              <FormField label="Patient Name">
                <input
                  value={formData.patientName}
                  onChange={(e) => updateForm("patientName", e.target.value)}
                  placeholder="e.g., John Doe"
                  className="input"
                 
                />
              </FormField>
              <FormField label="Age">
                <input
                  type="number"
                  value={formData.patientAge}
                  onChange={(e) => updateForm("patientAge", e.target.value)}
                  placeholder="e.g., 65"
                  className="input"
                 
                />
              </FormField>
              <FormField label="Gender">
                <select
                  value={formData.patientGender}
                  onChange={(e) => updateForm("patientGender", e.target.value)}
                  className="input"
                 
                >
                  <option value="">Select...</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </FormField>
              <FormField label="Contact Number">
                <input
                  value={formData.patientContact}
                  onChange={(e) => updateForm("patientContact", e.target.value)}
                  placeholder="e.g., (555) 123-4567"
                  className="input"
                />
              </FormField>
            </div>
          </div>

          {/* Clinical Information (Plain Language) */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <FileText size={20} className="text-purple-600" />
              <h2 className="text-lg font-semibold text-slate-900">What Brought the Patient In?</h2>
              <span className="text-xs text-slate-500">(Describe in plain language)</span>
            </div>
            <div className="space-y-4">
              <FormField label="Main Complaint">
                <input
                  value={formData.chiefComplaint}
                  onChange={(e) => updateForm("chiefComplaint", e.target.value)}
                  placeholder="e.g., Severe knee pain"
                  className="input"
                 
                />
              </FormField>

              <FormField label="Describe the Problem" className="col-span-2">
                <textarea
                  value={formData.problemDescription}
                  onChange={(e) => updateForm("problemDescription", e.target.value)}
                  placeholder="e.g., Patient has severe arthritis in right knee. Bone grinding on bone. Can't walk properly or climb stairs."
                  className="input"
                  rows={3}
                 
                />
              </FormField>

              <FormField label="Symptoms">
                <textarea
                  value={formData.symptomsDescription}
                  onChange={(e) => updateForm("symptomsDescription", e.target.value)}
                  placeholder="e.g., Constant pain, swelling, stiffness, difficulty walking, can't sleep due to pain"
                  className="input"
                  rows={2}
                 
                />
              </FormField>

              <FormField label="How Long Has This Been a Problem?">
                <input
                  value={formData.howLongProblem}
                  onChange={(e) => updateForm("howLongProblem", e.target.value)}
                  placeholder="e.g., Over 2 years, getting worse"
                  className="input"
                 
                />
              </FormField>

              <FormField label="What Did We Diagnose?">
                <textarea
                  value={formData.diagnosisInWords}
                  onChange={(e) => updateForm("diagnosisInWords", e.target.value)}
                  placeholder="e.g., Severe wear and tear arthritis of the right knee with damaged cartilage"
                  className="input"
                  rows={2}
                 
                />
              </FormField>
            </div>
          </div>

          {/* Treatment Information */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Hospital size={20} className="text-emerald-600" />
              <h2 className="text-lg font-semibold text-slate-900">Treatment Provided</h2>
              <span className="text-xs text-slate-500">(What we did to help)</span>
            </div>
            <div className="space-y-4">
              <FormField label="Treatment Summary">
                <textarea
                  value={formData.treatmentDescription}
                  onChange={(e) => updateForm("treatmentDescription", e.target.value)}
                  placeholder="e.g., Patient tried physical therapy for 6 months but didn't improve. Replaced the damaged knee with an artificial one."
                  className="input"
                  rows={3}
                 
                />
              </FormField>

              <FormField label="Procedures/Surgery Performed">
                <textarea
                  value={formData.proceduresDescription}
                  onChange={(e) => updateForm("proceduresDescription", e.target.value)}
                  placeholder="e.g., Knee replacement surgery - removed damaged knee joint and put in artificial joint"
                  className="input"
                  rows={2}
                 
                />
              </FormField>

              <FormField label="Medications Given">
                <textarea
                  value={formData.medicationsGiven}
                  onChange={(e) => updateForm("medicationsGiven", e.target.value)}
                  placeholder="e.g., Pain medicine, blood thinner to prevent clots, anti-inflammatory medicine"
                  className="input"
                  rows={2}
                />
              </FormField>
            </div>
          </div>

          {/* Hospital Stay Details */}
          <div className="card p-5">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Hospital Stay Details</h2>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Admission Date">
                <input
                  type="date"
                  value={formData.admissionDate}
                  onChange={(e) => updateForm("admissionDate", e.target.value)}
                  className="input"
                 
                />
              </FormField>
              <FormField label="Discharge Date">
                <input
                  type="date"
                  value={formData.dischargeDate}
                  onChange={(e) => updateForm("dischargeDate", e.target.value)}
                  className="input"
                 
                />
              </FormField>
              <FormField label="Total Days in Hospital">
                <input
                  type="number"
                  value={formData.lengthOfStay}
                  onChange={(e) => updateForm("lengthOfStay", e.target.value)}
                  placeholder="e.g., 4"
                  className="input"
                 
                />
              </FormField>
            </div>
          </div>

          {/* Facilities & Services */}
          <div className="card p-5">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Facilities & Services Used</h2>
            <div className="space-y-4">
              <FormField label="Room Type">
                <select
                  value={formData.roomCategory}
                  onChange={(e) => updateForm("roomCategory", e.target.value)}
                  className="input"
                 
                >
                  <option value="">Select...</option>
                  <option value="General Ward">General Ward (shared room)</option>
                  <option value="Semi-Private">Semi-Private (2 beds)</option>
                  <option value="Private">Private Room</option>
                  <option value="ICU">Intensive Care Unit (ICU)</option>
                  <option value="Deluxe">Deluxe Room</option>
                </select>
              </FormField>

              <FormField label="Special Facilities Used">
                <textarea
                  value={formData.specialFacilities}
                  onChange={(e) => updateForm("specialFacilities", e.target.value)}
                  placeholder="e.g., Operating theater, Recovery room, X-ray machine, MRI scanner"
                  className="input"
                  rows={2}
                />
              </FormField>

              <FormField label="Services Provided">
                <textarea
                  value={formData.servicesProvided}
                  onChange={(e) => updateForm("servicesProvided", e.target.value)}
                  placeholder="e.g., 24-hour nursing care, Physical therapy sessions, Meals, Doctor visits"
                  className="input"
                  rows={2}
                />
              </FormField>

              <div className="grid grid-cols-2 gap-4">
                <FormField label="Hospital Name">
                  <input
                    value={formData.hospitalName}
                    onChange={(e) => updateForm("hospitalName", e.target.value)}
                    placeholder="e.g., City General Hospital"
                    className="input"
                  />
                </FormField>
                <FormField label="Department">
                  <input
                    value={formData.departmentName}
                    onChange={(e) => updateForm("departmentName", e.target.value)}
                    placeholder="e.g., Orthopedics"
                    className="input"
                   
                  />
                </FormField>
                <FormField label="Attending Doctor">
                  <input
                    value={formData.attendingDoctor}
                    onChange={(e) => updateForm("attendingDoctor", e.target.value)}
                    placeholder="e.g., Dr. Sarah Mitchell"
                    className="input"
                   
                  />
                </FormField>
              </div>
            </div>
          </div>

          {/* Insurance & Billing */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <DollarSign size={20} className="text-amber-600" />
              <h2 className="text-lg font-semibold text-slate-900">Insurance & Billing</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Insurance Company">
                <input
                  value={formData.insuranceCompany}
                  onChange={(e) => updateForm("insuranceCompany", e.target.value)}
                  placeholder="e.g., ABC Health Insurance"
                  className="input"
                 
                />
              </FormField>
              <FormField label="Policy Number">
                <input
                  value={formData.policyNumber}
                  onChange={(e) => updateForm("policyNumber", e.target.value)}
                  placeholder="e.g., ABC-POL-123456"
                  className="input"
                 
                />
              </FormField>
              <FormField label="Claim Type">
                <select
                  value={formData.claimType}
                  onChange={(e) => updateForm("claimType", e.target.value)}
                  className="input"
                >
                  <option value="professional">Professional</option>
                  <option value="institutional">Institutional</option>
                  <option value="pharmacy">Pharmacy</option>
                </select>
              </FormField>
              <FormField label="Claim ID (optional)">
                <input
                  value={formData.claimId}
                  onChange={(e) => updateForm("claimId", e.target.value)}
                  placeholder="auto-generated if blank"
                  className="input"
                />
              </FormField>
              <FormField label="Estimated Total Cost ($)" className="col-span-2">
                <input
                  type="number"
                  step="0.01"
                  value={formData.estimatedTotalCost}
                  onChange={(e) => updateForm("estimatedTotalCost", e.target.value)}
                  placeholder="e.g., 48000"
                  className="input"
                 
                />
                <p className="mt-1 text-xs text-slate-500">AI will break this down into room, procedure, medication, and other charges</p>
              </FormField>
            </div>
          </div>

          {/* Document Upload */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Paperclip size={20} className="text-blue-600" />
              <h2 className="text-lg font-semibold text-slate-900">Supporting Documents</h2>
              <span className="text-xs text-slate-500">(Bills, Prescriptions, Reports)</span>
              <select
                value={formData.docType}
                onChange={(e) => updateForm("docType", e.target.value)}
                className="ml-auto rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600"
              >
                {DOC_TYPES.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-slate-300 px-6 py-8 text-center hover:border-blue-400 hover:bg-blue-50/50 transition-colors">
              <Upload size={32} className="text-slate-400" />
              <div>
                <span className="text-sm font-medium text-slate-700">Click to upload files</span>
                <p className="text-xs text-slate-500 mt-1">PDF, PNG, JPG or TIFF (max 20 MB each)</p>
              </div>
              <input
                type="file"
                multiple
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => {
                  // Copy the files out now: e.target.files is a live FileList that
                  // the value reset below empties, and React may run the updater
                  // later (it does once the form has pending state updates).
                  const picked = Array.from(e.target.files ?? []);
                  e.target.value = ""; // lets the same file be picked again after removal
                  if (picked.length > 0) {
                    setUploadedFiles(prev => [...prev, ...picked]);
                  }
                }}
              />
            </label>

            {uploadedFiles.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-sm font-medium text-slate-700">Uploaded Files ({uploadedFiles.length}):</div>
                {uploadedFiles.map((file, idx) => (
                  <div key={idx} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
                    <div className="flex items-center gap-2">
                      <Paperclip size={16} className="text-slate-400" />
                      <span className="text-sm text-slate-700">{file.name}</span>
                      <span className="text-xs text-slate-500">({(file.size / 1024).toFixed(1)} KB)</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setUploadedFiles(prev => prev.filter((_, i) => i !== idx))}
                      className="text-slate-400 hover:text-red-600 transition-colors"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              icon={<FileText size={18} />}
            >
              Review Claim
              <ArrowRight size={18} />
            </Button>
          </div>
        </form>
      )}

      {/* Step 2: Review what the hospital entered -- nothing generated */}
      {step === "review" && (
        <div className="space-y-5">
          {submitError && (
            <Alert type="error" title="Submit failed">
              {submitError}
              {rejectedFiles.length > 0 && <RejectedNotice rejected={rejectedFiles} />}
            </Alert>
          )}

          {(!formData.patientId.trim() || !formData.insuranceCompany.trim()) && (
            <Alert type="warning" title="Missing details needed for adjudication">
              {!formData.patientId.trim() && "Patient ID is blank. "}
              {!formData.insuranceCompany.trim() && "Insurance company is blank. "}
              The claim can still be saved as a draft, but the insurer cannot evaluate it until these are filled in.
            </Alert>
          )}

          <div className="card p-5">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">Medical Codes</h2>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
              <div className="font-medium text-slate-900 mb-1">Not assigned yet</div>
              ICD-10, CPT and medication codes are not guessed from this form. After you submit, they are extracted
              from the uploaded documents (each code cites the exact text it came from) and confirmed by a certified
              coder before the claim goes to the insurer.
              {uploadedFiles.length === 0 && (
                <div className="mt-2 font-medium text-amber-700">
                  No documents attached — codes can't be extracted until documents are uploaded to this claim.
                </div>
              )}
            </div>
          </div>

          <div className="card p-5">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">Claim Details (as entered)</h2>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <ReviewField label="Patient ID" value={formData.patientId} />
              <ReviewField label="Patient" value={[formData.patientName, formData.patientAge && `${formData.patientAge} y`, formData.patientGender].filter(Boolean).join(", ")} />
              <ReviewField label="Insurance company" value={formData.insuranceCompany} />
              <ReviewField label="Policy number" value={formData.policyNumber} />
              <ReviewField label="Hospital" value={[formData.hospitalName, formData.departmentName].filter(Boolean).join(" — ")} />
              <ReviewField label="Attending doctor" value={formData.attendingDoctor} />
              <ReviewField label="Admission" value={[formData.admissionDate, formData.dischargeDate].filter(Boolean).join(" to ")} />
              <ReviewField label="Estimated total cost" value={formData.estimatedTotalCost && formatAmount(formData.estimatedTotalCost)} />
              <ReviewField label="Chief complaint" value={formData.chiefComplaint} wide />
              <ReviewField label="Diagnosis (in words)" value={formData.diagnosisInWords} wide />
              <ReviewField label="Procedures" value={formData.proceduresDescription} wide />
              <ReviewField label="Treatment" value={formData.treatmentDescription} wide />
              <ReviewField label="Medications" value={formData.medicationsGiven} wide />
            </dl>
          </div>

          <div className="card p-5">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">Documents</h2>
            {uploadedFiles.length === 0 ? (
              <p className="text-sm text-slate-500">No documents attached.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {uploadedFiles.map((file, idx) => (
                  <li key={idx} className="rounded bg-slate-50 px-3 py-1.5 text-slate-700">
                    {file.name} <span className="text-slate-400">· {(file.size / 1024).toFixed(0)} KB</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between card p-4">
            <Button
              variant="outline"
              onClick={handleEditAndRegenerate}
              icon={<FileText size={16} />}
            >
              Edit Details
            </Button>
            <Button
              variant="primary"
              size="lg"
              onClick={handleApproveAndSubmit}
              icon={<CheckCircle size={18} />}
            >
              Submit Claim
            </Button>
          </div>
        </div>
      )}

      {/* Step 4: Submitting */}
      {step === "submitting" && (
        <div className="card p-12">
          <LoadingSpinner size={48} message="Submitting claim to insurance company..." />
          <p className="mt-4 text-center text-sm text-slate-600">
            Your technical claim documentation is being securely transmitted...
          </p>
        </div>
      )}
    </div>
  );
}

// Helper Components
function RejectedNotice({ rejected }: { rejected: Rejected[] }) {
  return (
    <ul className="mt-2 space-y-0.5 text-sm text-amber-700">
      {rejected.map((r, i) => (
        <li key={i}>
          <span className="font-medium">{r.filename}</span> — {r.message}
        </li>
      ))}
    </ul>
  );
}

function StepIndicator({ number, label, active, completed }: { number: number; label: string; active: boolean; completed: boolean }) {
  return (
    <div className="flex flex-col items-center">
      <div
        className={`flex h-10 w-10 items-center justify-center rounded-full border-2 font-semibold text-sm ${
          completed
            ? "border-emerald-500 bg-emerald-500 text-white"
            : active
            ? "border-blue-600 bg-blue-600 text-white"
            : "border-slate-300 bg-white text-slate-400"
        }`}
      >
        {completed ? <CheckCircle size={20} /> : number}
      </div>
      <span className={`mt-2 text-xs font-medium text-center ${active || completed ? "text-slate-700" : "text-slate-400"}`}>
        {label}
      </span>
    </div>
  );
}

function FormField({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={className}>
      <label className="block text-sm font-medium text-slate-700 mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

function ReviewField({ label, value, wide }: { label: string; value?: string | false; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900 whitespace-pre-wrap">{value || <span className="font-normal text-slate-400">—</span>}</dd>
    </div>
  );
}

function formatAmount(value: string): string {
  const amount = parseFloat(value);
  return Number.isFinite(amount) ? `$${amount.toLocaleString()}` : "—";
}
