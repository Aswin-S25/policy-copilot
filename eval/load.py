import json
from pathlib import Path

from eval.models import GoldenCase

def load_golden_cases(
    path: str = 'eval/golden.json',
) -> list[GoldenCase]:
    
    data = json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )
    
    return [
        GoldenCase(
            id=item["id"],
            question=item["question"],
            relevant_chunk_ids=set(
                item["relevant_chunk_ids"]
            ),
            answerable=item["answerable"],
        )
        for item in data
    ]