from eval.latency_bench import percentile, spread
from eval.lib.regression import check_regressions, floor_checks_passed

BASELINE = {
    "dataset": {"cases": 138},
    "retrieval": {"recall_at_5": 0.90, "mrr": 0.95},
    "answers": {"refusal_accuracy": 0.97, "faithfulness": 0.99,
                "relevance": 0.99, "citation_correctness": 0.99},
}


def run(**overrides):
    current = {
        "dataset": {"cases": 138},
        "retrieval": {**BASELINE["retrieval"]},
        "answers": {**BASELINE["answers"]},
    }
    for path, value in overrides.items():
        section, name = path.split("__")
        current[section][name] = value
    return check_regressions(BASELINE, current)


def failed(checks):
    return {(c.metric, c.kind) for c in checks if not c.passed}


def test_identical_run_passes():
    assert failed(run()) == set()


def test_drop_within_tolerance_passes():
    assert failed(run(retrieval__recall_at_5=0.875)) == set()


def test_drop_beyond_tolerance_fails():
    assert failed(run(retrieval__mrr=0.91)) == {("retrieval.mrr", "regression")}


def test_floor_fails_even_without_regression():
    baseline = {**BASELINE, "answers": {**BASELINE["answers"], "faithfulness": 0.88}}
    current = {**baseline, "answers": {**baseline["answers"]}}

    checks = check_regressions(baseline, current)

    assert failed(checks) == {("answers.faithfulness", "floor")}
    assert not floor_checks_passed(checks)


def test_different_dataset_fails_and_skips_comparisons():
    current = {"dataset": {"cases": 80}, "retrieval": {"recall_at_5": 0.5, "mrr": 0.9}}

    checks = check_regressions(BASELINE, current, sections=("retrieval",))

    assert ("dataset.cases", "dataset") in failed(checks)
    assert not any(c.kind == "regression" for c in checks)


def test_retrieval_only_ignores_answer_metrics():
    current = {"dataset": {"cases": 138}, "retrieval": {**BASELINE["retrieval"]}}

    checks = check_regressions(BASELINE, current, sections=("retrieval",))

    assert all(c.metric.startswith(("retrieval", "dataset")) for c in checks)


def test_no_baseline_checks_floors_only():
    checks = check_regressions(None, {"dataset": {"cases": 1},
                                      "retrieval": {"recall_at_5": 0.9, "mrr": 0.9}},
                               sections=("retrieval",))

    assert {c.kind for c in checks} == {"floor"}


def test_percentile_nearest_rank_and_spread():
    values = list(range(1, 11))
    assert percentile(values, 50) == 5
    assert percentile(values, 95) == 10
    assert spread(list(range(10)), 5) == [0, 2, 4, 6, 8]


# ---- judge robustness and coverage --------------------------------------------

def test_judge_timeout_is_a_case_failure_not_a_crash(monkeypatch):
    import httpx

    import eval.lib.judge as judge

    calls = []

    class SlowJudge:
        def chat(self, **kwargs):
            calls.append(kwargs)
            raise httpx.ReadTimeout("judge took too long")

    monkeypatch.setattr(judge, "client", SlowJudge())

    result = judge.judge_answer(question="q", answer="a [Source 1]", context="c")

    assert result is None                     # counted as a judge failure
    assert len(calls) >= 2                    # retried before giving up
    assert calls[0]["keep_alive"] == judge.KEEP_ALIVE


def test_low_judge_coverage_fails_floor():
    current = {
        "dataset": {"cases": 138},
        "retrieval": {**BASELINE["retrieval"]},
        "answers": {**BASELINE["answers"], "answer_coverage": 1.0, "judge_coverage": 0.90},
    }

    checks = check_regressions(BASELINE, current)

    assert failed(checks) == {("answers.judge_coverage", "floor")}
    assert not floor_checks_passed(checks)
