"""Phase 7 step 3b: which retrieval + answerability gate should the app use?

Configurations (all roles, top-5):
  dense         current app: dense, per-chunk cosine >= 0.45
  hybrid        hybrid RRF top-5, always sent to the LLM
  hybrid_gated  hybrid, refused before the LLM unless best dense
                cosine >= 0.45 or lexical retrieval matched

Part 1 (fast, no LLM): retrieval metrics, pre-LLM refusals, gate sweep.
Part 2 (--answers, slow): end-to-end refusal accuracy + judged quality.
Answers are cached in eval/reports/gating_answers.json keyed by
case id + context chunk ids; reruns resume where they stopped.

    python -m eval.experiments.compare_gating
    python -m eval.experiments.compare_gating --answers
    python -m eval.experiments.compare_gating --answers --no-seed
"""
import argparse
import json
import os
from pathlib import Path

from ollama import Client

import app.rag.llm
import eval.lib.judge
from app.core.authz import ALL_ROLES
from app.core.db import SessionLocal
from app.retrieval.hybrid import retrieve_hybrid_with_signals
from app.rag.pipeline import answer_from_chunks
from app.retrieval.dense import retrieve_chunks
from app.retrieval.search import CANDIDATE_K
from eval.lib.answers import looks_like_refusal
from eval.lib.judge import judge_answer
from eval.lib.load import load_golden_cases

TOP_K = 5
# Rejected in step 3b (see app/retrieval/search.py): kept here only to reproduce
# the experiment.
MIN_DENSE_SCORE = 0.45
CONFIGS = ["dense", "hybrid", "hybrid_gated"]
SWEEP = [0.35, 0.40, 0.45, 0.50, 0.55]

OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "300"))
app.rag.llm.client = Client(host=app.rag.llm.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)
eval.lib.judge.client = Client(host=eval.lib.judge.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)

CACHE_PATH = Path("eval/reports/gating_answers.json")
SEED_PATH = Path("eval/reports/cap_answers.json")
REPORT_PATH = Path("eval/reports/gating_comparison.json")


def passes_relevance_gate(best_dense_score, lexical_hits, min_dense_score=MIN_DENSE_SCORE):
    return best_dense_score >= min_dense_score or lexical_hits > 0


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def print_table(title, header, rows):
    print()
    print(title)
    print("-" * len(title))
    print(f"{'':<34}" + "".join(f"{h:>14}" for h in header))
    for label, values in rows:
        print(f"{label:<34}" + "".join(
            f"{v:>14.3f}" if isinstance(v, float) else f"{v:>14}" for v in values
        ))


def retrieve_case(db, question):
    dense = retrieve_chunks(
        db=db, query=question, top_k=TOP_K,
        min_score=MIN_DENSE_SCORE, roles=ALL_ROLES,
    )
    hybrid = retrieve_hybrid_with_signals(
        db=db, query=question, top_k=TOP_K,
        candidate_k=CANDIDATE_K, roles=ALL_ROLES,
    )
    allowed = passes_relevance_gate(hybrid.best_dense_score, hybrid.lexical_hits)
    contexts = {
        "dense": dense,
        "hybrid": hybrid.chunks,
        "hybrid_gated": hybrid.chunks if allowed else [],
    }
    return contexts, hybrid.best_dense_score, hybrid.lexical_hits


def recall_and_rr(chunks, relevant):
    ids = [str(c.chunk_id) for c in chunks]
    recall = len(set(ids) & relevant) / len(relevant)
    rr = next((1 / i for i, cid in enumerate(ids, 1) if cid in relevant), 0.0)
    return recall, rr


def answer(case, chunks, cache, seed):
    if not chunks:
        # Refused before the LLM: deterministic, never cached.
        response = answer_from_chunks(question=case.question, retrieved=[])
        return {"answer": response.answer, "refused": True, "judge": None}

    key = "|".join([case.id, *(str(c.chunk_id) for c in chunks)])

    if key not in cache and key in seed:
        cache[key] = {k: seed[key][k] for k in ("answer", "refused", "judge")}

    if key not in cache:
        response = answer_from_chunks(question=case.question, retrieved=chunks)
        refused = looks_like_refusal(response.answer)
        judged = None if refused else judge_answer(
            question=case.question,
            answer=response.answer,
            context=response.context,
        )
        cache[key] = {
            "answer": response.answer,
            "refused": refused,
            "judge": None if judged is None else {
                "faithfulness": judged.faithfulness,
                "relevance": judged.relevance,
                "citation_correctness": judged.citation_correctness,
            },
        }
        print(f"  generated: {case.id}", flush=True)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return cache[key]


def main(with_answers: bool, use_seed: bool):
    cases = load_golden_cases()
    answerable = [c for c in cases if c.answerable]
    unanswerable = [c for c in cases if not c.answerable]

    db = SessionLocal()
    try:
        contexts, signals = {}, {}
        for case in cases:
            contexts[case.id], dense_best, lexical_hits = retrieve_case(db, case.question)
            signals[case.id] = (dense_best, lexical_hits)
            db.rollback()
    finally:
        db.close()

    # ---- Part 1: retrieval + pre-LLM refusals (no LLM) ------------------
    print_table(
        f"Retrieval on answerable cases (n={len(answerable)})",
        CONFIGS,
        [
            ("Recall@5", [mean(recall_and_rr(contexts[c.id][n], c.relevant_chunk_ids)[0] for c in answerable) for n in CONFIGS]),
            ("MRR", [mean(recall_and_rr(contexts[c.id][n], c.relevant_chunk_ids)[1] for c in answerable) for n in CONFIGS]),
        ],
    )
    print_table(
        "Refused before the LLM (empty context)",
        CONFIGS,
        [
            (f"answerable (n={len(answerable)}) [bad]", [sum(1 for c in answerable if not contexts[c.id][n]) for n in CONFIGS]),
            (f"unanswerable (n={len(unanswerable)}) [good]", [sum(1 for c in unanswerable if not contexts[c.id][n]) for n in CONFIGS]),
        ],
    )

    sweep_rows = []
    for threshold in SWEEP:
        for label, use_lexical in (("dense+lexical", True), ("dense only", False)):
            def blocked(c):
                best, hits = signals[c.id]
                return not passes_relevance_gate(best, hits if use_lexical else 0, threshold)
            sweep_rows.append((
                f"{label:<14} @ {threshold:.2f}",
                [sum(map(blocked, answerable)), sum(map(blocked, unanswerable))],
            ))
    print_table(
        "Gate sweep: cases blocked before the LLM",
        [f"answ. (n={len(answerable)})", f"unans. (n={len(unanswerable)})"],
        sweep_rows,
    )

    print("\nAnswerable cases blocked by hybrid_gated:")
    for c in answerable:
        if not contexts[c.id]["hybrid_gated"]:
            best, hits = signals[c.id]
            print(f"  {c.id:<16} dense={best:.3f} lexical={hits}  {c.question}")
    print("Unanswerable cases passed by hybrid_gated:")
    for c in unanswerable:
        if contexts[c.id]["hybrid_gated"]:
            best, hits = signals[c.id]
            print(f"  {c.id:<16} dense={best:.3f} lexical={hits}  {c.question}")

    report = {
        "signals": {cid: {"best_dense": b, "lexical_hits": h} for cid, (b, h) in signals.items()},
    }

    # ---- Part 2: end-to-end answers (slow) -------------------------------
    if with_answers:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
        seed = (
            json.loads(SEED_PATH.read_text(encoding="utf-8"))
            if use_seed and SEED_PATH.exists() else {}
        )

        results, failed = {}, set()
        for case in cases:
            for n in CONFIGS:
                try:
                    results[(case.id, n)] = answer(case, contexts[case.id][n], cache, seed)
                except Exception as exc:  # timeout / connection reset: rerun to retry
                    print(f"  FAILED {case.id} {n}: {type(exc).__name__}: {exc}", flush=True)
                    failed.add(case.id)

        if failed:
            print(f"\n{len(failed)} cases failed and are excluded; rerun to retry: {sorted(failed)}")
        done = [c for c in cases if c.id not in failed]
        ans = [c for c in done if c.answerable]
        unans = [c for c in done if not c.answerable]

        def refused(c, n):
            return results[(c.id, n)]["refused"]

        def judged(n, field):
            return mean(
                results[(c.id, n)]["judge"][field]
                for c in done if results[(c.id, n)]["judge"]
            )

        rows = [
            (f"refusal accuracy (n={len(done)})", [mean((c.answerable != refused(c, n)) for c in done) for n in CONFIGS]),
            (f"answerable answered (n={len(ans)})", [mean(not refused(c, n) for c in ans) for n in CONFIGS]),
            (f"unanswerable refused (n={len(unans)})", [mean(refused(c, n) for c in unans) for n in CONFIGS]),
            ("faithfulness (judged)", [judged(n, "faithfulness") for n in CONFIGS]),
            ("relevance (judged)", [judged(n, "relevance") for n in CONFIGS]),
            ("citation correctness (judged)", [judged(n, "citation_correctness") for n in CONFIGS]),
            ("judged answers", [sum(1 for c in done if results[(c.id, n)]["judge"]) for n in CONFIGS]),
            ("LLM calls avoided by gate", [sum(1 for c in done if not contexts[c.id][n]) for n in CONFIGS]),
        ]
        print_table("End-to-end answers", CONFIGS, rows)

        for n in CONFIGS:
            wrong = [c.id for c in unans if not refused(c, n)]
            print(f"{n}: unanswerable cases ANSWERED: {wrong or 'none'}")

        report["answers"] = {label: dict(zip(CONFIGS, vals)) for label, vals in rows}

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="generate and judge answers (slow)")
    parser.add_argument("--no-seed", action="store_true", help="do not reuse cap experiment answers")
    args = parser.parse_args()
    main(args.answers, not args.no_seed)
