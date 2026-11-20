from app.core.db import SessionLocal
from eval.lib.load import load_golden_cases
from eval.lib.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case
)


STRATERGIES = ["hybrid", "diverse_2", "diverse_3"]

def run_strategy(db, cases, strategy):
    results = []
    
    for case in cases:
        result = evaluate_retrieval_case(
            db=db,
            case=case,
            top_k=5,
            strategy=strategy
        )
        
        results.append(result)
        
    return calculate_metrics(results)


def run_comparison():
    cases = load_golden_cases()
    db = SessionLocal()
    try:
        metrics = {}
        
        for strategy in STRATERGIES:
            print(f"\n Running {strategy.upper()} retrieval")
            print ("-" * 40)
            
            metrics[strategy] = run_strategy(
                db,
                cases,
                strategy
            )
            
        print()
        print("=" * 75)
        print("HYBRID VS DOCUMENT DIVERSITY")
        print("=" * 75)
        
        for metric_name, attribute in [
            ("Recall@5", "recall_at_5"),
            ("MRR", "mrr")
        ]:
            
            values = [
                getattr(metrics[strategy], attribute)
                for strategy in STRATERGIES
            ]
            
            print(
                f"{metric_name:<18}",
                f"{values[0]:<12.4f}",
                f"{values[1]:<12.4f}",
                f"{values[2]:<12.4f}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    run_comparison()