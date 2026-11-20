from app.core.db import SessionLocal
from app.retrieval.experimental.query_planner import plan_query

from eval.lib.load import load_golden_cases
from eval.lib.retrieval import evaluate_retrieval_case

def calculate_case_metrics(result):
    relevant = set(result.relevant_chunk_ids)
    retrieved = result.retrieved_chunk_ids
    
    if not relevant:
        return 0.0, 0.0

    hits = relevant.intersection(retrieved)
    recall = len(hits) / len(relevant)
    
    reciprocal_rank = 0.0
    
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            reciprocal_rank = 1/rank
            break
        
    return recall, reciprocal_rank


def run_diagonistics():
    cases = load_golden_cases()
    db = SessionLocal()
    
    lexical_count = 0
    better = 0
    worse = 0
    unchanged = 0
    mrr_better = 0
    mrr_worse = 0
    mrr_unchanged = 0

    
    try:
        print("=" * 90)
        print("QUERY ROUTER DIAGONSTICS")
        print("=" * 90)
        
        for case in cases:
            plan = plan_query(case.question)
            
            if plan.strategy != "lexical":
                continue
            
            lexical_count += 1
            
            auto_result = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="auto"
            )
            
            
            hybrid_result = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="hybrid"
            )
            
            
            auto_recall, auto_mrr = calculate_case_metrics(auto_result)
            hybrid_recall, hybrid_mrr = calculate_case_metrics(hybrid_result)
            
            # Recall@5 classification
            if auto_recall > hybrid_recall:
                better += 1
                status = "AUTO BETTER"
            elif auto_recall < hybrid_recall:
                worse += 1
                status = "AUTO WORSE"
            else:
                unchanged += 1
                status = "SAME RECALL"

            # MRR classification
            if auto_mrr > hybrid_mrr:
                mrr_better += 1
                mrr_status = "MRR IMPROVED"
            elif auto_mrr < hybrid_mrr:
                mrr_worse += 1
                mrr_status = "MRR DEGRADED"
            else:
                mrr_unchanged += 1
                mrr_status = "SAME MRR"

            
            print()
            print(f"Case: {case.id}")
            print(f"Query:  {case.question}")
            print(f"Status: {status}")
            print(f"MRR status: {mrr_status}")
            print(f"Planner stratergy: {plan.strategy}")
            
            print(
                f"Recall@5: Auto={auto_recall:.4f}, "
                f"Hybrid = {hybrid_recall:.4f}"
            )
            
            print(
                f"MRR: Auto={auto_mrr:.4f}, "
                f"Hybrid = {hybrid_mrr:.4f}"
            )
            
            auto_missing = (
                set(auto_result.relevant_chunk_ids)
                - set(auto_result.retrieved_chunk_ids)
            )
            
            hybrid_missing = (
                set(hybrid_result.relevant_chunk_ids)
                - set(hybrid_result.retrieved_chunk_ids)
            )
            
            print(f"Relevant chunks missed by Auto: {auto_missing}")
            print(f"Relevant chunks missed by Hybrid: {hybrid_missing}")
            
        print()
        print("=" * 90)
        print("SUMMARY")
        print("=" * 90)
        print(f"Queries routed to lexical : {lexical_count}")
        print(f"Auto better: {better}")
        print(f"Auto worse: {worse}")
        print(f"Same recall: {unchanged}")
        print(f"MRR improved: {mrr_better}")
        print(f"MRR degraded: {mrr_worse}")
        print(f"Same MRR: {mrr_unchanged}")
        
    finally:
        db.close()
    
    
if __name__ == "__main__":
    run_diagonistics()
