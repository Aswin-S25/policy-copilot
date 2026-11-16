"""Compare per-document caps (none, 2, 3, 4) on top of hybrid retrieval.

Reports, separately for single-document and multi-document questions:
  * retrieval: Recall@5, MRR, required-document coverage
  * which queries lose (or gain) relevant chunks under each cap vs no cap
  * answer quality: refusals, LLM-judge faithfulness / relevance / citation
    correctness
  * citation completeness: share of required documents and relevant chunks
    that the final answer actually cites

Answers are only generated for cases where at least one cap changes the
top-5 set; for every other case all configurations see identical context,
so their answers would be identical too. Generated answers and judge scores
are cached in eval/reports/cap_answers.json, so the run can be resumed.

    python -m eval.compare_caps                 # retrieval analysis only
    python -m eval.compare_caps --answers       # + answer quality (slow)
"""
import argparse
import os
import json

from ollama import Client

import app.llm
import eval.judge
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.authz import ALL_ROLES
from app.citations import exact_citations
from app.db import SessionLocal
from app.diversity import apply_document_cap
from app.hybrid_retrieval import retrieve_hybrid
from app.rag import answer_from_chunks
from eval.answers import looks_like_refusal
from eval.judge import judge_answer
from eval.load import load_golden_cases

CONFIGS = {"no_cap": None, "cap_2": 2, "cap_3": 3, "cap_4": 4}
TOP_K = 5
CANDIDATE_K = 20
OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "300"))

# The ollama client has no timeout by default, so a server restart (e.g. an
# Ollama auto-update) leaves the request hanging forever. Use bounded clients
# for this experiment only.
app.llm.client = Client(host=app.llm.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)
eval.judge.client = Client(host=eval.judge.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)

CACHE_PATH = Path("eval/reports/cap_answers.json")
REPORT_PATH = Path("eval/reports/cap_comparison.json")


def retrieve(db, question):
    candidates = retrieve_hybrid(
        db=db, query=question, top_k=CANDIDATE_K, candidate_k=CANDIDATE_K,
        roles=ALL_ROLES,
    )
    out = {}
    for name, cap in CONFIGS.items():
        out[name] = (
            candidates[:TOP_K]
            if cap is None
            else apply_document_cap(candidates, top_k=TOP_K, max_per_document=cap)
        )
    return out


def chunk_info(db):
    rows = db.execute(text("""
        SELECT c.id::text, c.document_id::text, coalesce(s.section_path, '')
        FROM chunks c LEFT JOIN sections s ON s.id = c.section_id
    """)).all()
    return {cid: (doc, path) for cid, doc, path in rows}


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def retrieval_scores(retrieved, relevant, info):
    ids = [str(c.chunk_id) for c in retrieved]
    hit = set(ids) & relevant
    recall = len(hit) / len(relevant)
    rr = next((1 / i for i, cid in enumerate(ids, 1) if cid in relevant), 0.0)
    required_docs = {info[c][0] for c in relevant}
    covered_docs = {info[c][0] for c in hit}
    return recall, rr, len(covered_docs) / len(required_docs)


def concentration(retrieved):
    """(unique documents, max chunks from a single document, underfilled?)."""
    counts = defaultdict(int)
    for chunk in retrieved:
        counts[str(chunk.document_id)] += 1
    return (
        len(counts),
        max(counts.values(), default=0),
        float(len(retrieved) < TOP_K),
    )


def answer_case(question, retrieved, relevant, info, cache, key):
    if key in cache:
        return cache[key]

    response = answer_from_chunks(question=question, retrieved=retrieved)
    by_source = {c.source_number: c.chunk_id for c in response.citations}
    cited = {by_source[n] for n in exact_citations(response.answer) if n in by_source}

    required_docs = {info[c][0] for c in relevant}
    cited_docs = {info[c][0] for c in cited if c in info}

    judged = None
    if not looks_like_refusal(response.answer):
        judged = judge_answer(
            question=question, answer=response.answer, context=response.context
        )

    cache[key] = {
        "answer": response.answer,
        "refused": looks_like_refusal(response.answer),
        "cited_chunk_ids": sorted(cited),
        "chunk_citation_recall": len(cited & relevant) / len(relevant),
        "doc_citation_recall": len(cited_docs & required_docs) / len(required_docs),
        "judge": None if judged is None else {
            "faithfulness": judged.faithfulness,
            "relevance": judged.relevance,
            "citation_correctness": judged.citation_correctness,
        },
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return cache[key]


def concentration(retrieved):
    """(unique documents, max chunks from a single document, underfilled?)."""
    counts = defaultdict(int)
    for chunk in retrieved:
        counts[str(chunk.document_id)] += 1
    return (
        len(counts),
        max(counts.values(), default=0),
        float(len(retrieved) < TOP_K),
    )


def print_table(title, header, rows):
    print()
    print(title)
    print("-" * len(title))
    print(f"{'':<26}" + "".join(f"{h:>10}" for h in header))
    for label, values in rows:
        print(f"{label:<26}" + "".join(
            f"{v:>10.3f}" if isinstance(v, float) else f"{v:>10}" for v in values
        ))


def main(with_answers: bool):
    cases = [c for c in load_golden_cases() if c.relevant_chunk_ids]
    db = SessionLocal()
    try:
        info = chunk_info(db)
        retrieved = {}
        for case in cases:
            retrieved[case.id] = retrieve(db, case.question)
            db.rollback()
    finally:
        db.close()

    group_of = {
        c.id: "multi_doc" if len({info[r][0] for r in c.relevant_chunk_ids}) > 1 else "single_doc"
        for c in cases
    }
    groups = {
        "single_doc": [c for c in cases if group_of[c.id] == "single_doc"],
        "multi_doc": [c for c in cases if group_of[c.id] == "multi_doc"],
        "all": cases,
    }
    names = list(CONFIGS)

    # ---- retrieval -------------------------------------------------------
    scores = {
        (c.id, n): retrieval_scores(retrieved[c.id][n], c.relevant_chunk_ids, info)
        for c in cases for n in names
    }
    for metric, idx in (("Recall@5", 0), ("MRR", 1), ("Required-document coverage", 2)):
        print_table(
            f"{metric} (hybrid top-{TOP_K}, {CANDIDATE_K} candidates)",
            names,
            [(f"{g} (n={len(cs)})", [mean(scores[(c.id, n)][idx] for c in cs) for n in names])
             for g, cs in groups.items()],
        )

    # ---- lost / gained chunks -------------------------------------------
    changes = defaultdict(list)
    for case in cases:
        base = {str(c.chunk_id) for c in retrieved[case.id]["no_cap"]} & case.relevant_chunk_ids
        for n in names[1:]:
            now = {str(c.chunk_id) for c in retrieved[case.id][n]} & case.relevant_chunk_ids
            lost, gained = base - now, now - base
            if lost or gained:
                changes[n].append((case, lost, gained))

    print_table(
        "Queries whose relevant chunks change vs no cap",
        names[1:],
        [(f"{label} {g}", [sum(1 for c, l, gn in changes[n] if (l if label == 'lose' else gn) and group_of[c.id] == g) for n in names[1:]])
         for label in ("lose", "gain") for g in ("single_doc", "multi_doc")],
    )
    for n in names[1:]:
        print(f"\n{n}: queries that LOSE relevant chunks")
        for case, lost, gained in changes[n]:
            if not lost:
                continue
            paths = "; ".join(sorted(info[c][1] for c in lost))
            extra = f"  (+gained {len(gained)})" if gained else ""
            print(f"  [{group_of[case.id]:<10}] {case.id:<16} -{len(lost)}/{len(case.relevant_chunk_ids)}{extra}  {case.question}")
            print(f"  {'':<12} lost: {paths}")
        gains = [(c, g) for c, l, g in changes[n] if g and not l]
        if gains:
            print(f"{n}: queries that only GAIN: " + ", ".join(f"{c.id}(+{len(g)})" for c, g in gains))

    # ---- document concentration ----------------------------------------
    # Diversity is a means, not a goal: report it so it can be weighed
    # against the recall it costs, never read as a quality metric by itself.
    conc = {
        (c.id, n): concentration(retrieved[c.id][n])
        for c in cases for n in names
    }
    for metric, idx in (
        ("Unique documents in top-5", 0),
        ("Max chunks from one document", 1),
        ("Underfill rate (< top-k returned)", 2),
    ):
        print_table(
            metric,
            names,
            [(f"{g} (n={len(cs)})", [mean(conc[(c.id, n)][idx] for c in cs) for n in names])
             for g, cs in groups.items()],
        )

    report = {"retrieval": {
        g: {n: {
                **dict(zip(("recall_at_5", "mrr", "doc_coverage"),
                           [mean(scores[(c.id, n)][i] for c in cs) for i in range(3)])),
                **dict(zip(("unique_docs", "max_chunks_per_doc", "underfill_rate"),
                           [mean(conc[(c.id, n)][i] for c in cs) for i in range(3)])),
            }
            for n in names}
        for g, cs in groups.items()
    }}
    if not with_answers and REPORT_PATH.exists():
        # Keep the (expensive) answer-quality results from a previous run.
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if "answers" in previous:
            report["answers"] = previous["answers"]

    if with_answers:
        affected = [
            c for c in cases
            if len({tuple(str(x.chunk_id) for x in retrieved[c.id][n]) for n in names}) > 1
        ]
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
        unique = {
            (c.id, tuple(str(x.chunk_id) for x in retrieved[c.id][n]))
            for c in affected for n in names
        }
        print(f"\nAnswer evaluation: {len(affected)} affected cases, "
              f"{len(unique)} unique contexts ({sum(1 for u in unique if '|'.join([u[0], *u[1]]) in cache)} cached)", flush=True)

        answers = {}
        failed = set()
        done = 0
        for case in affected:
            for n in names:
                ids = [str(x.chunk_id) for x in retrieved[case.id][n]]
                key = "|".join([case.id, *ids])
                fresh = key not in cache
                try:
                    answers[(case.id, n)] = answer_case(
                        case.question, retrieved[case.id][n], case.relevant_chunk_ids, info, cache, key
                    )
                except Exception as exc:  # timeout / connection reset: rerun to retry
                    print(f"  FAILED {case.id} {n}: {type(exc).__name__}: {exc}", flush=True)
                    failed.add(case.id)
                    continue
                if fresh:
                    done += 1
                    print(f"  generated {done}: {case.id} {n}", flush=True)

        if failed:
            print(f"\n{len(failed)} cases had failures and are excluded; rerun to retry: {sorted(failed)}")
        affected = [c for c in affected if c.id not in failed]

        agroups = {
            "single_doc": [c for c in affected if group_of[c.id] == "single_doc"],
            "multi_doc": [c for c in affected if group_of[c.id] == "multi_doc"],
            "all": affected,
        }

        def judged(cs, n, field):
            return mean(answers[(c.id, n)]["judge"][field] for c in cs if answers[(c.id, n)]["judge"])

        report["answers"] = {}
        for g, cs in agroups.items():
            rows = [
                ("refusal rate", [mean(answers[(c.id, n)]["refused"] for c in cs) for n in names]),
                ("faithfulness", [judged(cs, n, "faithfulness") for n in names]),
                ("relevance", [judged(cs, n, "relevance") for n in names]),
                ("citation correctness", [judged(cs, n, "citation_correctness") for n in names]),
                ("doc citation recall", [mean(answers[(c.id, n)]["doc_citation_recall"] for c in cs) for n in names]),
                ("chunk citation recall", [mean(answers[(c.id, n)]["chunk_citation_recall"] for c in cs) for n in names]),
            ]
            print_table(f"Answer quality - {g} affected cases (n={len(cs)})", names, rows)
            report["answers"][g] = {
                "n": len(cs),
                **{label: dict(zip(names, vals)) for label, vals in rows},
            }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="also generate and judge answers")
    main(parser.parse_args().answers)
