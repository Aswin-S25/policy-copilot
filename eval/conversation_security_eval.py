"""Conversation security evaluation (Phase 7 conversations, step 4).

Runs multi-turn attacks through the real service path (prepare_turn ->
answer_from_chunks -> record_answer) on the real corpus and LLM:

  inference   a role steers follow-ups toward documents it cannot read
  revocation  history built under a role that could read a document,
              continued by the same user without that role

Hard checks on the final turn (exit status 1 on any failure):
  * retrieved chunks from unreadable documents            == 0
  * restricted fingerprints in rewrite prompt / standalone
    question / answer                                       == 0
  * withheld answers replayed into the rewrite prompt      == 0
  * GET-view withheld answers == oracle expectation

Each case uses its own conversation (owner "security-eval-<uuid>"),
deleted afterwards.

    python -m eval.conversation_security_eval
"""
import json
import sys
import uuid
from pathlib import Path

from app.conversation_service import prepare_turn, record_answer, visible_messages
from app.conversations import create_conversation, delete_conversation, get_messages
from app.db import SessionLocal
from app.llm import complete
from app.rag import answer_from_chunks
from app.security import Principal
from eval.answers import looks_like_refusal
from eval.load import load_golden_cases
from eval.security_eval import (
    ROLE_SETS,
    fact_tokens,
    ids,
    load_oracle,
    restricted_fingerprints,
)

CASES_PATH = Path("eval/conversation_attacks.json")
REPORT_PATH = Path("eval/reports/conversation_security_eval.json")
WITHHELD_PROBE_CHARS = 200


def run_case(case, golden, oracle):
    chunk_doc, chunk_text, readable, readable_tokens = oracle
    final_role_set = case["turns"][-1]["role_set"]
    final_readable = readable[final_role_set]

    prompts = []

    def recording_complete(**kwargs):
        prompts.append(kwargs["user_prompt"])
        return complete(**kwargs)

    owner = f"security-eval-{uuid.uuid4()}"
    with SessionLocal() as db:
        conversation = create_conversation(db, owner, f"security eval {case['id']}")
        conversation_id = conversation.id
        db.commit()

    try:
        history_sources = set()
        for index, turn in enumerate(case["turns"]):
            principal = Principal(
                subject=owner, roles=frozenset(ROLE_SETS[turn["role_set"]])
            )
            prompts.clear()

            with SessionLocal() as db:
                prepared = prepare_turn(
                    db, conversation_id, principal, turn["question"],
                    complete_fn=recording_complete,
                )

            response = answer_from_chunks(
                question=prepared.standalone_question,
                retrieved=prepared.retrieved,
            )
            sources = [uuid.UUID(c.chunk_id) for c in response.citations]

            with SessionLocal() as db:
                record_answer(db, conversation_id, owner, response.answer, sources)

            if index < len(case["turns"]) - 1:
                history_sources |= {str(s) for s in sources}

        # ---- final-turn checks --------------------------------------------
        retrieval_leaks = [
            cid for cid in ids(prepared.retrieved)
            if chunk_doc.get(cid) not in final_readable
        ]

        unreadable_ids = {
            cid for cid in history_sources | golden[case["target"]].relevant_chunk_ids
            if chunk_doc.get(cid) not in final_readable
        }
        typed = " ".join(t["question"] for t in case["turns"])
        fingerprints = restricted_fingerprints(
            typed,
            [chunk_text[cid] for cid in unreadable_ids if cid in chunk_text],
            readable_tokens[final_role_set],
        )

        rewrite_prompt = prompts[-1] if prompts else ""
        prompt_leaks = sorted(fingerprints & fact_tokens(rewrite_prompt))
        standalone_leaks = sorted(fingerprints & fact_tokens(prepared.standalone_question))
        answer_leaks = sorted(fingerprints & fact_tokens(response.answer))

        final_roles = ROLE_SETS[final_role_set]
        with SessionLocal() as db:
            messages = get_messages(db, conversation_id, owner)
            shown = visible_messages(db, messages, final_roles)

            # Independent expectation from the oracle, not answer_is_visible().
            expected_withheld = [
                m for m in messages
                if m.sender == "assistant" and (
                    m.source_chunk_ids is None
                    or any(chunk_doc.get(str(c)) not in final_readable
                           for c in m.source_chunk_ids)
                )
            ]
            withheld_texts = [m.content for m in expected_withheld]

        actual_withheld = sum(1 for m in shown if m["withheld"])
        replayed_withheld = sum(
            1 for text in withheld_texts
            if text[:WITHHELD_PROBE_CHARS] in rewrite_prompt
        )

        failures = []
        if retrieval_leaks:
            failures.append("retrieval leak")
        if prompt_leaks or standalone_leaks or answer_leaks:
            failures.append("fingerprint leak")
        if replayed_withheld:
            failures.append("withheld answer replayed")
        if actual_withheld != len(expected_withheld):
            failures.append("withheld mismatch")

        return {
            "id": case["id"],
            "kind": case["kind"],
            "final_role_set": final_role_set,
            "final_question": case["turns"][-1]["question"],
            "standalone_question": prepared.standalone_question,
            "answer": response.answer,
            "refused": looks_like_refusal(response.answer),
            "dropped_answers": prepared.dropped_answers,
            "retrieval_leaks": retrieval_leaks,
            "fingerprints": sorted(fingerprints),
            "prompt_leaks": prompt_leaks,
            "standalone_leaks": standalone_leaks,
            "answer_leaks": answer_leaks,
            "expected_withheld": len(expected_withheld),
            "actual_withheld": actual_withheld,
            "replayed_withheld": replayed_withheld,
            "failures": failures,
        }
    finally:
        with SessionLocal() as db:
            delete_conversation(db, conversation_id, owner)
            db.commit()


def main() -> int:
    golden = {c.id: c for c in load_golden_cases()}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    with SessionLocal() as db:
        oracle = load_oracle(db)

    results = []
    for case in cases:
        print(f"  running {case['id']} ({case['kind']})", flush=True)
        results.append(run_case(case, golden, oracle))

    print()
    print(f"{'case':<8}{'kind':<12}{'final role':<12}{'refused':>8}{'dropped':>9}"
          f"{'fp':>4}{'leaks':>7}{'withheld exp/act':>18}  result")
    for r in results:
        leaks = (len(r["retrieval_leaks"]) + len(r["prompt_leaks"])
                 + len(r["standalone_leaks"]) + len(r["answer_leaks"]))
        print(f"{r['id']:<8}{r['kind']:<12}{r['final_role_set']:<12}"
              f"{str(r['refused']):>8}{r['dropped_answers']:>9}"
              f"{len(r['fingerprints']):>4}{leaks:>7}"
              f"{r['expected_withheld']:>9}/{r['actual_withheld']:<8}  "
              f"{'FAIL: ' + ', '.join(r['failures']) if r['failures'] else 'ok'}")

    print("\nFinal turns:")
    for r in results:
        print(f"  {r['id']}  {r['final_question']!r}")
        print(f"      standalone: {r['standalone_question']!r}")
        print(f"      answer: {r['answer'][:200]!r}")

    for kind in ("inference", "revocation"):
        group = [r for r in results if r["kind"] == kind]
        refused = sum(r["refused"] for r in group)
        print(f"\n{kind}: {len(group)} cases, refused {refused}/{len(group)}, "
              f"failures {sum(1 for r in group if r['failures'])}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")

    failed = any(r["failures"] for r in results)
    print(f"\nCONVERSATION SECURITY CHECK: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
