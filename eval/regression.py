import json
from pathlib import Path

BASELINE_PATH = Path("eval/baseline.json")

MAX_RECALL_DROP = 0.03

def load_baseline():
    if not BASELINE_PATH.exists():
        raise FileNotFoundError(
            f"Baseline not found: {BASELINE_PATH}"
        )

    return json.loads(
        BASELINE_PATH.read_text(
            encoding="utf-8"
        )
    )

def check_recall_regression(
    baseline_recall: float,
    current_recall: float,
    max_drop: float = MAX_RECALL_DROP,
) -> bool:

    drop = baseline_recall - current_recall

    print()
    print("Recall Regression Check")
    print("-----------------------")
    print(f"Baseline Recall@5: {baseline_recall:.4f}")
    print(f"Current Recall@5:  {current_recall:.4f}")
    print(f"Drop:              {drop:.4f}")
    print(f"Allowed drop:      {max_drop:.4f}")

    if drop > max_drop:
        print("RESULT: FAIL")
        return False

    print("RESULT: PASS")
    return True


def run_regression_check(
    current_recall: float,
) -> bool:

    baseline = load_baseline()

    baseline_recall = baseline[
        "retrieval"
    ]["recall_at_5"]

    return check_recall_regression(
        baseline_recall=baseline_recall,
        current_recall=current_recall,
    )