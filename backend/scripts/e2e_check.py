"""
End-to-end smoke test for MediAudit-X, run against a live backend +
Elasticsearch (NOT mocked). Exercises the actual acceptance checklist
from the build spec, not just "does the server respond."

Requires: `uvicorn app.main:app --port 8000` already running in another
terminal, and the full ingestion pipeline (create_indices, load_sample_data,
load_real_cms_policies, ingest_synthea_samples) already completed.

Run with:
    cd backend && source venv/bin/activate && python3 scripts/e2e_check.py
"""
import json
import sys
import time

import requests

BASE = "http://localhost:8000"
RESULTS = []  # (name, passed: bool, detail: str)


def record(name, passed, detail=""):
    RESULTS.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail else ""))


def get(path, **kw):
    return requests.get(f"{BASE}{path}", timeout=15, **kw)


def post(path, **kw):
    return requests.post(f"{BASE}{path}", timeout=15, **kw)


def stream_adjudicate(claim_id, timeout=60):
    """POSTs /claims/{id}/adjudicate and collects every SSE event."""
    events = []
    with requests.post(f"{BASE}/claims/{claim_id}/adjudicate", stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        event_name, data_lines = "message", []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip("\r")
            if line == "":
                if data_lines:
                    try:
                        data = json.loads("".join(data_lines))
                    except json.JSONDecodeError:
                        data = {"_raw": "".join(data_lines)}
                    events.append((event_name, data))
                    if event_name == "done":
                        break
                event_name, data_lines = "message", []
                continue
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
    return events


def main():
    print("=" * 70)
    print("MediAudit-X end-to-end check")
    print("=" * 70)

    # 1. Health
    try:
        r = get("/health")
        record("Backend /health responds", r.status_code == 200 and r.json().get("status") == "ok", f"status={r.status_code} body={r.text}")
    except Exception as e:
        record("Backend /health responds", False, str(e))
        print("\nBackend unreachable -- is `uvicorn app.main:app --port 8000` running? Stopping here.")
        sys.exit(1)

    # 2. Claims list + duplicate check
    r = get("/claims?limit=200")
    claims = r.json() if r.status_code == 200 else []
    record("GET /claims returns claims", r.status_code == 200 and len(claims) > 0, f"{len(claims)} claims returned")
    claim_ids = [c.get("claim_id") for c in claims]
    dupes = {cid for cid in claim_ids if claim_ids.count(cid) > 1}
    record("No duplicate claim_ids in insurance-claims", len(dupes) == 0, f"duplicated: {sorted(dupes)}" if dupes else "clean")

    have = {c.get("claim_id"): c for c in claims}

    # 3. Drug interaction case: CLM-1001 (Eliquis/Toradol, real fixture)
    if "CLM-1001" in have:
        events = stream_adjudicate("CLM-1001")
        alerts = [d for e, d in events if e == "interaction_alert"]
        done = next((d for e, d in events if e == "done"), None)
        real_llm_reasoning = any(e == "reasoning_step" and d.get("step") == "agent_reasoning" for e, d in events)
        record(
            "CLM-1001 drug interaction (Eliquis/Toradol) caught",
            bool(alerts) and any(a.get("severity") == "Contraindicated" for a in alerts),
            f"{len(alerts)} alert(s): {[a.get('severity') for a in alerts]}",
        )
        record(
            "CLM-1001 decision = DENIED (contraindicated interaction should block approval)",
            done is not None and done.get("status") == "DENIED",
            f"status={done.get('status') if done else 'no done event'}",
        )
        record(
            "CLM-1001 real LLM reasoning present (not just deterministic sweep)",
            real_llm_reasoning,
            "found agent_reasoning step" if real_llm_reasoning else "only saw deterministic tool_call steps -- check LLM credentials",
        )
        record(
            "CLM-1001 audit ledger entry written",
            done is not None and bool(done.get("ledger_entry", {}).get("ledger_id")),
            f"ledger_id={done.get('ledger_entry', {}).get('ledger_id') if done else None}",
        )
    else:
        record("CLM-1001 present in insurance-claims", False, "claim not found -- was load_sample_data run?")

    # 4. Positive step-therapy case: CLM-1008 (if the 18 Sept additions were loaded)
    if "CLM-1008" in have:
        events = stream_adjudicate("CLM-1008")
        done = next((d for e, d in events if e == "done"), None)
        traj = done.get("trajectory_result") if done else None
        record(
            "CLM-1008 step-therapy correctly METs (positive case)",
            traj is not None and traj.get("step_therapy_met") is True,
            f"trajectory_result={traj}",
        )
    else:
        print("[skip] CLM-1008 not found -- skipping positive step-therapy check (only relevant if you loaded the 18 Sept sample additions)")

    # 5. Shortfall case: PAT-883910 clinical history
    r = get("/patients/PAT-883910/history")
    hist = r.json() if r.status_code == 200 else []
    record("GET /patients/{id}/history returns real encounter data", r.status_code == 200 and len(hist) > 0, f"{len(hist)} records")

    # 6. Real CMS policy match: CLM-2003 (only claim whose payer_name matches the real Medicare LCD exactly)
    if "CLM-2003" in have:
        events = stream_adjudicate("CLM-2003")
        done = next((d for e, d in events if e == "done"), None)
        matched = done.get("matched_policy") if done else None
        record(
            "CLM-2003 matches the real CMS Medicare LCD policy",
            matched is not None and matched.get("policy_id", "").startswith("POL-MEDICARE-LCD"),
            f"matched_policy={matched.get('policy_id') if matched else None}",
        )
    else:
        print("[skip] CLM-2003 not found -- skipping real-CMS-policy-match check (needs ingest_synthea_samples to have run)")

    # 7. Audit chain integrity (direct import, since there's no /audit/verify-chain endpoint built yet)
    try:
        sys.path.insert(0, ".")
        from app.tools.audit_ledger import verify_chain
        intact = verify_chain("CLM-1001")
        record("audit_ledger.verify_chain('CLM-1001') reports intact", intact is True, f"verify_chain returned {intact}")
    except Exception as e:
        record("audit_ledger.verify_chain import/call", False, str(e))

    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in RESULTS if p)
    print(f"SUMMARY: {passed}/{len(RESULTS)} checks passed")
    print("=" * 70)
    for name, p, detail in RESULTS:
        if not p:
            print(f"  FAILED: {name}" + (f" ({detail})" if detail else ""))


if __name__ == "__main__":
    main()
