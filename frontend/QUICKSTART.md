# MediAudit-X Quick Start Guide

## Setup Instructions

### 1. Install Dependencies

```bash
cd /Users/chandakji2204/forge-defcon1/src/mediaudit-x/frontend
npm install
```

### 2. Start the Application

```bash
npm run dev
```

The application will be available at **http://localhost:3000**

### 3. Start the Backend (Required)

In a separate terminal:

```bash
cd /Users/chandakji2204/forge-defcon1/src/mediaudit-x/backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn app.main:app --reload --port 8000
```

Backend API will be available at **http://localhost:8000**

## Hackathon Demo Script (15-20 minutes)

### Part 1: Introduction (2 minutes)

**"MediAudit-X is a zero-hallucination clinical claims auditor that combines Elasticsearch hybrid search, ES|QL temporal reasoning, and AI-powered analysis to help insurance reviewers make evidence-backed claim decisions."**

Key points:
- Every decision is grounded in searchable evidence
- AI recommends, evidence verifies, human decides
- Dual role experience: Hospital + Insurance Reviewer

### Part 2: Hospital Experience (3 minutes)

1. **Switch to Hospital Role**
   - Click "Switch to Hospital" button in sidebar
   - Show role indicator: "CityCare Hospital / Hospital Administrator"

2. **Dashboard**
   - Point out hospital-specific stats: Draft, Submitted, In Review, Approved
   - Quick action: "Create New Claim"

3. **Code Mapping Demo**
   - Navigate to `http://localhost:3000/claims/CLM-1001/mapping` (or any claim)
   - Show automatic mapping:
     - "Type II Diabetes Mellitus" → ICD-10 E11.9 (98% confidence)
     - "Total Knee Replacement" → CPT 27447 (96% confidence)
   - Highlight low-confidence mapping requiring review
   - Show alternative code suggestions
   - Demonstrate confirmation workflow

**Key Message:** *"The system automatically normalizes hospital terminology into standardized medical codes, flagging uncertain mappings for human review."*

### Part 3: Insurance Reviewer Experience (10 minutes)

1. **Switch to Insurance Reviewer Role**
   - Click "Switch to Insurance" in sidebar
   - Show "Dr. Sarah Mitchell / Insurance Reviewer"

2. **Review Queue** (`/review-queue`)
   - Show stats: Needs Review, AI recommendations
   - Filter by "Approve Recommended"
   - Point out AI recommendation badges in table
   - Click "Review" on CLM-2026-00142

**Key Message:** *"Reviewers see claims prioritized by AI analysis, with clear recommendation indicators."*

3. **Claim Review Workspace - Overview Tab**

   **Claim Status Timeline:**
   - Visual workflow: Draft → Mapping → Validated → Submitted → AI Review → Human Review → Decision
   - Shows current position in workflow

   **AI Recommendation Card:**
   - "APPROVE RECOMMENDED" with clear visual indicator
   - Shows: Policy matched, Evidence sources, Drug interactions, Step therapy
   - Important disclaimer: *"AI recommendation is advisory only"*

   **Claim Summary:**
   - Generated decision letter with evidence

**Key Message:** *"The AI provides a recommendation, but makes clear it's advisory—the human reviewer has final authority."*

4. **Clinical History Tab**
   - Show patient timeline: Jan 12 → Jul 18 (187 days of PT)
   - Highlight temporal reasoning: "187 days exceeds 180-day requirement"
   - Visual timeline with diagnosis, treatment, imaging, encounters

**Key Message:** *"ES|QL temporal queries verify step-therapy timelines against actual longitudinal patient history."*

5. **Policy & Guidelines Tab**
   - Show matched policy: POL-KNEE-042
   - Policy requirements with status badges:
     - ✓ Diagnosis requirement: SATISFIED
     - ✓ Conservative treatment: SATISFIED
     - ✓ Treatment duration: SATISFIED
     - ✓ Imaging evidence: SATISFIED
   - Evidence citations linked to requirements

**Key Message:** *"Hybrid BM25 + vector search with RRF matches claims against payer policy documents."*

6. **AI Assistant Tab** (Demo Interactive Chat)

   Type: **"Was the conservative treatment requirement satisfied?"**

   Expected response:
   ```
   Yes. The available clinical records support the requirement.

   Why:
   The applicable policy requires at least 180 days of conservative treatment.
   
   The patient timeline contains:
   • Jan 12 — Physical therapy started
   • Jul 18 — Physical therapy documented
   
   Observed interval: 187 days
   
   Conclusion:
   Requirement: SATISFIED
   ```

   **Show evidence citations:**
   - [EV-18291] PT note — Jan 12, 2026
   - [EV-19281] PT note — Jul 18, 2026
   - [POL-042 §4.2] Conservative treatment requirement

   Try another: **"Why is this claim recommended for approval?"**

**Key Message:** *"Reviewers can ask natural language questions and get structured, evidence-backed answers with citations."*

7. **Human Decision Workflow**
   - Go back to Overview tab
   - Show Reviewer Decision Panel
   - Select "Approve Claim"
   - Enter comment: "Medical necessity criteria verified against applicable policy and clinical records. All requirements documented and satisfied."
   - Click "Submit Decision"
   - Confirmation modal shows:
     - Claim ID
     - AI recommendation: APPROVE RECOMMENDED
     - Your decision: APPROVED
     - Your comment
   - Confirm approval

**Key Message:** *"Final decision requires human reviewer action with mandatory comment for auditability."*

8. **Show Final State**
   - Claim status now: APPROVED
   - AI recommendation vs. Human decision both visible
   - Audit trail records entire process
   - Hash-chained ledger entry

### Part 4: Insufficient Evidence Scenario (3 minutes)

1. **Navigate to CLM-2026-00144**
   - Show AI recommendation: NEEDS_REVIEW
   - Status: Insufficient Evidence

2. **Clinical History Tab**
   - Show treatment gaps:
     - Mar 15 - Apr 20: 36 days
     - **Gap in records**
     - Jul 10 - Aug 5: 26 days
   - Total documented: 62 days vs. 180 required

3. **AI Assistant**
   - Ask: "Why is this claim flagged for human review?"
   - Response explains: "Cannot establish continuous 6-month treatment. Gap period not documented."

4. **Show Policy Requirements**
   - Conservative treatment: INSUFFICIENT_EVIDENCE
   - "Available records do not establish continuous 180-day treatment"

**Key Message:** *"The system distinguishes 'insufficient evidence' from 'requirement not satisfied'—missing records don't become false negatives."*

### Part 5: Technical Highlights (2 minutes)

**Architecture:**
- **Elasticsearch**: Hybrid BM25 + 768-dim vector search with RRF
- **ES|QL**: Bi-temporal queries for step-therapy verification
- **Agent Builder**: Multi-round Claude tool-use loop via AWS Bedrock
- **SSE Streaming**: Live agent reasoning
- **Audit Ledger**: SHA-256 hash-chained, tamper-evident
- **FHIR**: Real Synthea-generated patient data

**Zero-Hallucination Property:**
- Final APPROVE/DENY decision computed deterministically from tool results
- Never left to LLM to state
- Falls back to deterministic no-LLM tool sweep if LLM fails

**Key Message:** *"This isn't a chatbot with database access—it's a deterministic adjudication engine that uses an LLM to orchestrate retrieval and explain results."*

## Key Demo Claims

### CLM-2026-00142 (APPROVAL)
- **Patient**: John Doe
- **Procedure**: Total Knee Replacement
- **Scenario**: All requirements satisfied
- **Use for**: Full happy path demo

### CLM-2026-00144 (INSUFFICIENT EVIDENCE)
- **Patient**: Michael Brown
- **Procedure**: Total Knee Replacement
- **Scenario**: Gap in treatment records
- **Use for**: Evidence limitation handling

### CLM-2026-00143 (HUMAN REVIEW)
- **Patient**: Sarah Smith
- **Procedure**: Spinal Fusion
- **Scenario**: Conflicting evidence
- **Use for**: Complex case requiring judgment

### CLM-2026-00145 (DENIAL)
- **Patient**: Priya Sharma
- **Procedure**: Cosmetic Rhinoplasty
- **Scenario**: Does not meet medical necessity
- **Use for**: Denial workflow

## Troubleshooting

### Frontend won't start
```bash
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Backend not responding
- Check if backend is running on port 8000
- Verify environment variables in backend/.env
- Check Elasticsearch connection

### Claims not loading
- Ensure backend data has been loaded:
  ```bash
  cd backend
  python -m app.ingestion.load_sample_data
  python -m app.ingestion.load_real_cms_policies
  python -m app.ingestion.ingest_synthea_samples
  ```

### Chat not working
- Chat uses demo responses (no backend API required)
- Check console for errors
- Ensure claimId is valid

## Tips for Effective Demo

1. **Practice the flow** - Run through once before presenting
2. **Use CLM-2026-00142 first** - It's the clean approval scenario
3. **Emphasize evidence** - Click citations, show evidence drawer
4. **Show the distinction** - AI recommends vs. human decides
5. **Highlight Elasticsearch** - Hybrid search, ES|QL, temporal queries
6. **Be ready for questions**:
   - "What if the AI is wrong?" → Human has final authority
   - "How do you prevent hallucinations?" → Deterministic decision engine
   - "What about scalability?" → Elasticsearch handles millions of documents
   - "Real-time updates?" → SSE streaming for live agent reasoning

## Feature Highlights Summary

✅ **Role-based experience** (Hospital + Insurance)
✅ **Automatic code mapping** with confidence scores
✅ **Review queue** with filtering and AI recommendations
✅ **Claim status timeline** showing workflow progress
✅ **AI recommendation card** with evidence summary
✅ **Interactive AI chat** with structured responses and citations
✅ **Policy requirements** with clear status indicators
✅ **Patient timeline** with temporal evidence
✅ **Human decision workflow** with mandatory comments
✅ **Confirmation modals** preventing accidental actions
✅ **Audit trail** with hash-chained ledger
✅ **Evidence citations** throughout the application
✅ **Insufficient evidence handling** (not fabricated negatives)
✅ **Professional healthcare UI** with consistent design

## Post-Demo Q&A Prep

**Q: Is the AI actually running?**
A: The backend uses real Claude via AWS Bedrock. Frontend demo has pre-built responses to ensure reliable demo flow. Real integration is in backend SSE endpoint.

**Q: How accurate is the code mapping?**
A: Uses real ICD-10, CPT, RxNorm codes. Mapping confidence based on term similarity. Production would use NLM APIs for validation.

**Q: Can reviewers override AI?**
A: Yes! That's the core design principle. AI recommends, human decides. Every decision requires reviewer action and comment.

**Q: What about edge cases?**
A: System distinguishes "insufficient evidence" from "requirement not satisfied." Missing data doesn't become a false negative.

**Q: How do you prevent claim fraud?**
A: Audit trail is hash-chained and tamper-evident. Every action logged with timestamp, actor, and full context.

**Q: What's your tech stack?**
A: Next.js 15, React 18, TypeScript, Tailwind CSS, Lucide icons, Elasticsearch, FastAPI, Claude (Bedrock), SSE streaming.

---

**Ready to demo!** 🚀
