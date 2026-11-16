"""Golden cases for the 9 policy documents added on 2026-11-15.

Each case labels relevant chunks as (document H1 title, section-path suffix).
Run `python -m eval.data_gen.new_golden_cases` to resolve them to chunk IDs and
append them to eval/golden.json (existing ids are replaced, so it is idempotent).
"""
import json
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal

HANDBOOK = "Employee Policy Handbook"
ISS = "Information Security Standard"
RHW = "Remote and Hybrid Work Policy"
ONB = "Onboarding and Probation Policy"
LND = "Learning and Development Policy"
AHG = "Anti-Harassment and Grievance Policy"
IR = "Incident Response Procedure"
ITA = "IT Asset Management Policy"
WB = "Wellbeing and Benefits Policy"
DCS = "Data Classification Standard"

# (id, category, question, [(doc, section suffix), ...])
CASES = [
    # --- direct ---------------------------------------------------------
    ("iss-001", "direct", "After how many minutes of inactivity must a company laptop lock automatically?", [(ISS, "ISS-01 Screen Lock")]),
    ("iss-002", "direct", "How quickly must critical security patches be installed?", [(ISS, "ISS-04 Patching Deadlines")]),
    ("iss-003", "direct", "How long is an approved removable media exception valid?", [(ISS, "ISS-03 Removable Media")]),
    ("rhw-001", "direct", "What is the standard hybrid schedule?", [(RHW, "1.2 Hybrid Schedule")]),
    ("rhw-002", "direct", "What are the core collaboration hours for remote employees?", [(RHW, "2.1 Core Collaboration Hours")]),
    ("rhw-003", "direct", "How much is the home office equipment allowance?", [(RHW, "2.3 Home Office Equipment")]),
    ("rhw-004", "direct", "How many days per year can I work from another country?", [(RHW, "3.1 Temporary Work Abroad")]),
    ("onb-001", "direct", "How long is the probation period?", [(ONB, "3.1 Probation Length")]),
    ("onb-002", "direct", "How long is a new employee assigned an onboarding buddy?", [(ONB, "2.2 Onboarding Buddy")]),
    ("onb-003", "direct", "Within how many days must mandatory training be completed after joining?", [(ONB, "2.3 Mandatory Training")]),
    ("lnd-001", "direct", "What is the annual learning budget per employee?", [(LND, "1.1 Annual Learning Budget")]),
    ("lnd-002", "direct", "How many days of paid study leave can employees take?", [(LND, "3.1 Study Leave Entitlement")]),
    ("ahg-001", "direct", "How long does an anti-harassment investigation normally take?", [(AHG, "3.1 Investigation Timeline")]),
    ("ahg-002", "direct", "Can harassment be reported anonymously?", [(AHG, "2.1 Reporting Channels")]),
    ("ir-001", "direct", "How quickly must a SEV1 page be acknowledged?", [(IR, "IR-SEV1 Critical")]),
    ("ir-002", "direct", "When must a postmortem be published after an incident?", [(IR, "4.1 Postmortem")]),
    ("ita-001", "direct", "How often are company laptops replaced?", [(ITA, "2.1 Refresh Cycle")]),
    ("ita-002", "direct", "How soon must equipment be returned after leaving the company?", [(ITA, "3.1 Leaving the Company")]),
    ("wb-001", "direct", "How many free counselling sessions does the EAP provide?", [(WB, "2.1 Employee Assistance Programme")]),
    ("wb-002", "direct", "How much is the quarterly wellness allowance?", [(WB, "3.1 Quarterly Wellness Allowance")]),
    ("dcs-001", "direct", "What are the four data classification levels?", [(DCS, "DCS-1 Public"), (DCS, "DCS-2 Internal"), (DCS, "DCS-3 Confidential"), (DCS, "DCS-4 Restricted")]),

    # --- interpretation -------------------------------------------------
    ("rhw-005", "interpretation", "I joined two months ago. Can I start working hybrid now?", [(RHW, "1.1 Who Can Work Remotely"), (ONB, "3.1 Probation Length")]),
    ("rhw-006", "interpretation", "Can my partner use my company laptop while I work from home?", [(RHW, "2.2 Home Workspace")]),
    ("lnd-003", "interpretation", "I failed my certification exam twice. Will the company pay for a third attempt?", [(LND, "2.1 Certification Reimbursement")]),
    ("lnd-004", "interpretation", "The company paid 1,200 USD for my certification six months ago. What happens if I resign now?", [(LND, "2.2 Clawback")]),
    ("dcs-002", "interpretation", "Can I email a customer's personal data to a colleague?", [(DCS, "DCS-4 Restricted"), (DCS, "2.2 Email and Chat")]),
    ("dcs-003", "interpretation", "A document has no classification label. How should I treat it?", [(DCS, "2.1 Labelling")]),
    ("ita-003", "interpretation", "Can I reinstall Windows on my old laptop before returning it?", [(ITA, "3.2 Data on Returned Devices")]),
    ("ita-004", "interpretation", "Can I check work email on my personal phone?", [(ITA, "4.1 Bring Your Own Device")]),
    ("ahg-003", "interpretation", "My manager is the one harassing me. Who should I report to?", [(AHG, "2.1 Reporting Channels")]),
    ("ir-003", "interpretation", "Should the incident commander also be debugging the outage?", [(IR, "2.1 Incident Commander")]),
    ("iss-004", "interpretation", "Can I work from a hotel Wi-Fi without the VPN?", [(ISS, "ISS-07 Public Wi-Fi")]),
    ("wb-003", "interpretation", "I didn't use my wellness allowance last quarter. Can I use double this quarter?", [(WB, "3.1 Quarterly Wellness Allowance")]),

    # --- multi-section (same document) ----------------------------------
    ("onb-004", "multi_section", "How does probation work, including reviews and extensions?", [(ONB, "3.1 Probation Length"), (ONB, "3.2 Probation Reviews"), (ONB, "3.3 Extending Probation")]),
    ("ir-004", "multi_section", "What is the difference between SEV1, SEV2 and SEV3 incidents?", [(IR, "IR-SEV1 Critical"), (IR, "IR-SEV2 Major"), (IR, "IR-SEV3 Minor")]),
    ("ahg-004", "multi_section", "What happens after I file a formal grievance, and can I appeal the result?", [(AHG, "3.1 Investigation Timeline"), (AHG, "3.3 Outcome and Appeal")]),
    ("lnd-005", "multi_section", "How do I get approval to spend my learning budget, and does it carry over?", [(LND, "1.1 Annual Learning Budget"), (LND, "1.2 Approval")]),
    ("dcs-004", "multi_section", "How should Restricted data be stored, shared and disposed of?", [(DCS, "DCS-4 Restricted"), (DCS, "2.2 Email and Chat"), (DCS, "2.3 Disposal")]),
    ("rhw-007", "multi_section", "What are the rules for working from abroad?", [(RHW, "3.1 Temporary Work Abroad"), (RHW, "3.2 Restricted Countries")]),

    # --- cross-document -------------------------------------------------
    ("cross-001", "cross_document", "What leave can I take during probation?", [(ONB, "3.4 Leave During Probation"), (HANDBOOK, "1.1 Annual Leave")]),
    ("cross-002", "cross_document", "How do I claim my wellness allowance?", [(WB, "3.2 Claiming the Allowance"), (HANDBOOK, "7.2 Expense Claims")]),
    ("cross-003", "cross_document", "What are all the rules for keeping my laptop secure?", [(ISS, "ISS-01 Screen Lock"), (ISS, "ISS-02 Disk Encryption"), (HANDBOOK, "5.1 Company Devices")]),
    ("cross-004", "cross_document", "Besides sick leave, what time off can I take for my health?", [(WB, "2.2 Mental Health Days"), (HANDBOOK, "1.3 Sick Leave")]),
    ("cross-005", "cross_document", "Is study leave counted against my annual leave?", [(LND, "3.1 Study Leave Entitlement"), (HANDBOOK, "1.1 Annual Leave")]),
    ("cross-006", "cross_document", "How do I share confidential information with an external partner?", [(DCS, "DCS-3 Confidential"), (HANDBOOK, "4.4 Data Sharing")]),
    ("cross-007", "cross_document", "What should I do if I find a security vulnerability or a security incident?", [(ISS, "ISS-05 Vulnerability Disclosure"), (HANDBOOK, "3.4 Security Incident Reporting")]),

    # --- identifier / policy-code lookups (query planner -> lexical) ----
    ("code-001", "identifier", "What does ISS-04 require?", [(ISS, "ISS-04 Patching Deadlines")]),
    ("code-002", "identifier", "Explain DCS-3", [(DCS, "DCS-3 Confidential")]),
    ("code-003", "identifier", "What is IR-SEV2?", [(IR, "IR-SEV2 Major")]),
    ("code-004", "identifier", "What is ISS-08 about?", [(ISS, "ISS-08 Clean Desk Rule")]),
    ("code-005", "identifier", "What format do ITA asset tags use?", [(ITA, "1.2 Asset Tags")]),

    # --- ambiguous ------------------------------------------------------
    ("amb-011", "ambiguous", "What is the allowance?", [(RHW, "2.3 Home Office Equipment"), (WB, "3.1 Quarterly Wellness Allowance")]),
    ("amb-012", "ambiguous", "What is the 30-day rule?", [(ONB, "2.3 Mandatory Training"), (ISS, "ISS-03 Removable Media"), (IR, "4.2 Action Items")]),
    ("amb-013", "ambiguous", "How do I report a problem?", [(AHG, "2.1 Reporting Channels"), (HANDBOOK, "3.4 Security Incident Reporting")]),

    # --- unanswerable ---------------------------------------------------
    ("unknown-011", "unanswerable", "What is the company's stock option vesting schedule?", []),
    ("unknown-012", "unanswerable", "How much is the on-call stipend per week?", []),
    ("unknown-013", "unanswerable", "Does the company sponsor work visas for relocation?", []),
    ("unknown-014", "unanswerable", "How many days of paid volunteering leave do employees get?", []),
]


def resolve(db) -> dict[tuple[str, str], list[str]]:
    rows = db.execute(text("""
        SELECT c.id::text, c.document_id::text, s.section_path, c.chunk_index
        FROM chunks c JOIN sections s ON s.id = c.section_id
        ORDER BY c.document_id, c.chunk_index
    """)).all()

    # Document H1 title = section_path of its first section.
    doc_names: dict[str, str] = {}
    for chunk_id, doc_id, path, idx in rows:
        doc_names.setdefault(doc_id, path)

    index: dict[tuple[str, str], list[str]] = {}
    for chunk_id, doc_id, path, idx in rows:
        index.setdefault((doc_names[doc_id], path), []).append(chunk_id)
    return index


def lookup(index, doc: str, suffix: str) -> list[str]:
    hits = [
        ids for (name, path), ids in index.items()
        if name == doc and (path == suffix or path.endswith(" > " + suffix))
    ]
    if len(hits) != 1:
        raise ValueError(f"{doc!r} / {suffix!r} matched {len(hits)} sections")
    return hits[0]


def main():
    db = SessionLocal()
    try:
        index = resolve(db)
    finally:
        db.close()

    new_cases = []
    for case_id, category, question, refs in CASES:
        chunk_ids = []
        for doc, suffix in refs:
            chunk_ids.extend(lookup(index, doc, suffix))
        new_cases.append({
            "id": case_id,
            "category": category,
            "question": question,
            "relevant_chunk_ids": chunk_ids,
            "answerable": bool(refs),
        })

    path = Path("eval/golden.json")
    existing = json.loads(path.read_text(encoding="utf-8"))
    new_ids = {c["id"] for c in new_cases}
    merged = [c for c in existing if c["id"] not in new_ids] + new_cases
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(new_cases)} cases; golden.json now has {len(merged)}.")


if __name__ == "__main__":
    main()
