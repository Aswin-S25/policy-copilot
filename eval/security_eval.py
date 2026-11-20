import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from ollama import Client
from sqlalchemy import text

import app.rag.llm
from app.core.authz import ALL_ROLES
from app.core.db import SessionLocal
from app.retrieval.lexical import retrieve_lexical
from app.rag.pipeline import answer_from_chunks
from app.retrieval.dense import retrieve_chunks
from app.retrieval.search import search_policies
from eval.lib.answers import looks_like_refusal
from eval.lib.load import load_golden_cases


ROLE_SETS = {
    "employee": ["employee"],
    "manager": ["manager"],
    "hr": ["hr"],
    "security": ["security"],
    "employee+security": ["employee", "security"],
    "no_document_roles": [],
}
TOP_K = 5
POOL_K = 20

OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "300"))
app.rag.llm.client = Client(host=app.rag.llm.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)

CACHE_PATH = Path("eval/reports/security_answers.json")
SEED_PATH = Path("eval/reports/gating_answers.json")
REPORT_PATH = Path("eval/reports/security_eval.json")

# Identifiers containing a digit (IR-SEV1, DCS-4, ISS-04) and numbers (15, 2.5).
FACT_TOKEN = re.compile(
    r"\b[A-Z]{2,}-[A-Z0-9-]*\d[A-Z0-9-]*\b|\b\d+(?:\.\d+)?\b"
)

def fact_tokens(value: str) -> set[str]:
    return set(FACT_TOKEN.findall(value))


def classify_access(required_docs: set[str], readable_docs: set[str]) -> str:
    if not required_docs:
        return "unanswerable"
    if required_docs <= readable_docs:
        return "authorized"
    if not required_docs & readable_docs:
        return "restricted"
    return "partial"


def restricted_fingerprints(
    question: str,
    restricted_texts: list[str],
    readable_tokens: set[str],
) -> set[str]:
    """Facts that exist only in unreadable relevant chunks: not in the
    question and nowhere in the corpus this role may read. If one appears
    in an answer, it did not come from the authorized context."""
    facts = set().union(*(fact_tokens(t) for t in restricted_texts))
    return facts - fact_tokens(question) - readable_tokens


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def ids(chunks) -> list[str]:
    return [str(c.chunk_id) for c in chunks]


# ---- oracle -----------------------------------------------------------------

def load_oracle(db):
    """Ground truth from raw SQL, deliberately not using readable_by()."""
    chunk_rows = db.execute(
        text("SELECT id::text, document_id::text, content FROM chunks")
    ).all()
    acl_rows = db.execute(
        text("SELECT document_id::text, role FROM document_acl WHERE permission = 'read'")
    ).all()

    chunk_doc = {cid: doc for cid, doc, _ in chunk_rows}
    chunk_text = {cid: content for cid, _, content in chunk_rows}

    doc_roles = defaultdict(set)
    for doc, role in acl_rows:
        doc_roles[doc].add(role)

    readable = {
        name: {doc for doc, granted in doc_roles.items() if granted & set(roles)}
        for name, roles in ROLE_SETS.items()
    }
    readable_tokens = {
        name: set().union(*(
            fact_tokens(chunk_text[cid])
            for cid, doc in chunk_doc.items() if doc in docs
        ))
        for name, docs in readable.items()
    }
    return chunk_doc, chunk_text, readable, readable_tokens


# ---- answers (Part 2) ---------------------------------------------------------

def get_answer(case, chunks, cache, seed) -> str:
    if not chunks:
        return answer_from_chunks(question=case.question, retrieved=[]).answer

    key = "|".join([case.id, *ids(chunks)])

    if key not in cache:
        if key in seed:
            cache[key] = {"answer": seed[key]["answer"]}
        else:
            response = answer_from_chunks(question=case.question, retrieved=chunks)
            cache[key] = {"answer": response.answer}
            print(f"  generated: {case.id}", flush=True)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    return cache[key]["answer"]


# ---- main -----------------------------------------------------------------------

def main(with_answers: bool) -> int:
    cases = load_golden_cases()

    db = SessionLocal()
    try:
        chunk_doc, chunk_text, readable, readable_tokens = load_oracle(db)

        leaks, checked = [], 0
        top5, all_roles_top5 = {}, {}

        for case in cases:
            all_roles_top5[case.id] = ids(
                search_policies(db=db, query=case.question, roles=ALL_ROLES)
            )
            for name, roles in ROLE_SETS.items():
                paths = {
                    "dense@20": retrieve_chunks(
                        db=db, query=case.question, top_k=POOL_K,
                        min_score=0.0, roles=roles,
                    ),
                    "lexical@20": retrieve_lexical(
                        db=db, query=case.question, top_k=POOL_K, roles=roles,
                    ),
                    "app@5": search_policies(
                        db=db, query=case.question, top_k=TOP_K, roles=roles,
                    ),
                }
                for path, chunks in paths.items():
                    for cid in ids(chunks):
                        checked += 1
                        if chunk_doc[cid] not in readable[name]:
                            leaks.append({
                                "case": case.id, "role_set": name,
                                "path": path, "chunk_id": cid,
                            })
                top5[(case.id, name)] = paths["app@5"]
            db.rollback()
    finally:
        db.close()

    # ---- Part 1: retrieval -------------------------------------------------
    print("\nRetrieval leakage")
    print("-----------------")
    print(f"Retrieved chunks checked: {checked}")
    print(f"Chunks from unreadable documents: {len(leaks)}")
    for leak in leaks[:20]:
        print(f"  LEAK {leak}")

    access = {}
    for case in cases:
        required = {chunk_doc[c] for c in case.relevant_chunk_ids}
        for name in ROLE_SETS:
            access[(case.id, name)] = classify_access(required, readable[name])

    answerable = [c for c in cases if c.relevant_chunk_ids]

    print("\nAccess classes per role set (answerable cases)")
    print("-----------------------------------------------")
    print(f"{'role set':<20}{'authorized':>12}{'restricted':>12}{'partial':>10}"
          f"{'auth R@5':>11}{'all-roles R@5':>15}")
    recall_report = {}
    for name in ROLE_SETS:
        counts = defaultdict(int)
        for case in answerable:
            counts[access[(case.id, name)]] += 1
        authorized = [c for c in answerable if access[(c.id, name)] == "authorized"]
        role_recall = mean(
            len(set(ids(top5[(c.id, name)])) & c.relevant_chunk_ids) / len(c.relevant_chunk_ids)
            for c in authorized
        )
        full_recall = mean(
            len(set(all_roles_top5[c.id]) & c.relevant_chunk_ids) / len(c.relevant_chunk_ids)
            for c in authorized
        )
        recall_report[name] = {
            **counts, "authorized_recall_at_5": role_recall,
            "all_roles_recall_at_5": full_recall,
        }
        print(f"{name:<20}{counts['authorized']:>12}{counts['restricted']:>12}"
              f"{counts['partial']:>10}{role_recall:>11.3f}{full_recall:>15.3f}")

    report = {
        "retrieval": {"checked": checked, "leaks": leaks, "per_role_set": recall_report},
    }
    fingerprint_leaks = []

    # ---- Part 2: answers ------------------------------------------------------
    if with_answers:
        role_sets = [n for n, roles in ROLE_SETS.items() if roles]
        restricted_docs = {
            doc for doc in set(chunk_doc.values())
            if not all(doc in readable[n] for n in role_sets)
        }
        targets = [
            c for c in answerable
            if {chunk_doc[r] for r in c.relevant_chunk_ids} & restricted_docs
        ]

        cache = (json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                 if CACHE_PATH.exists() else {})
        seed = (json.loads(SEED_PATH.read_text(encoding="utf-8"))
                if SEED_PATH.exists() else {})

        print(f"\nAnswer evaluation: {len(targets)} cases need a restricted document "
              f"x {len(role_sets)} role sets")

        rows, failed = [], []
        for case in targets:
            for name in role_sets:
                try:
                    answer = get_answer(case, top5[(case.id, name)], cache, seed)
                except Exception as exc:  # timeout / reset: rerun to retry
                    print(f"  FAILED {case.id} {name}: {type(exc).__name__}: {exc}", flush=True)
                    failed.append((case.id, name))
                    continue

                unreadable_relevant = [
                    chunk_text[c] for c in case.relevant_chunk_ids
                    if chunk_doc[c] not in readable[name]
                ]
                fingerprints = restricted_fingerprints(
                    case.question, unreadable_relevant, readable_tokens[name]
                )
                leaked = sorted(fingerprints & fact_tokens(answer))
                row = {
                    "case": case.id, "role_set": name,
                    "access": access[(case.id, name)],
                    "refused": looks_like_refusal(answer),
                    "fingerprints": sorted(fingerprints),
                    "leaked": leaked,
                    "question": case.question,
                    "answer": answer,
                }
                rows.append(row)
                if leaked:
                    fingerprint_leaks.append(row)

        by_class = defaultdict(list)
        for row in rows:
            by_class[row["access"]].append(row)

        restricted = by_class["restricted"]
        authorized = by_class["authorized"]
        partial = by_class["partial"]

        print("\nAnswers")
        print("-------")
        print(f"restricted  n={len(restricted):<4} refused={mean(r['refused'] for r in restricted):.3f}  "
              f"with fingerprints={sum(1 for r in restricted if r['fingerprints'])}  "
              f"fingerprint leaks={sum(1 for r in restricted if r['leaked'])}")
        print(f"authorized  n={len(authorized):<4} answered={mean(not r['refused'] for r in authorized):.3f}")
        print(f"partial     n={len(partial):<4} answered={mean(not r['refused'] for r in partial):.3f}")

        print("\nFingerprint leaks (restricted facts in the answer):")
        for row in fingerprint_leaks:
            print(f"  {row['case']:<14} {row['role_set']:<18} leaked={row['leaked']}")
            print(f"    {row['answer'][:300]}")
        if not fingerprint_leaks:
            print("  none")

        print("\nRestricted cases NOT refused (review: answered from readable documents?):")
        for row in restricted:
            if not row["refused"]:
                print(f"  {row['case']:<14} {row['role_set']:<18} {row['question']}")
                print(f"    {row['answer'][:300]}")

        print("\nAuthorized cases refused (quality, not security):")
        for row in authorized:
            if row["refused"]:
                print(f"  {row['case']:<14} {row['role_set']:<18} {row['question']}")

        if failed:
            print(f"\n{len(failed)} answers failed and are excluded; rerun to retry: {failed}")

        report["answers"] = {
            "restricted": {
                "n": len(restricted),
                "refusal_rate": mean(r["refused"] for r in restricted),
                "with_fingerprints": sum(1 for r in restricted if r["fingerprints"]),
                "fingerprint_leaks": sum(1 for r in restricted if r["leaked"]),
            },
            "authorized": {
                "n": len(authorized),
                "answered_rate": mean(not r["refused"] for r in authorized),
            },
            "partial": {"n": len(partial)},
            "rows": rows,
        }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")

    failed_check = bool(leaks) or bool(fingerprint_leaks)
    print(f"\nSECURITY CHECK: {'FAIL' if failed_check else 'PASS'}")
    return 1 if failed_check else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="also generate answers (slow)")
    sys.exit(main(parser.parse_args().answers))