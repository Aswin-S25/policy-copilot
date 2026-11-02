import json
from dataclasses import dataclass

from ollama import Client


OLLAMA_HOST = "http://localhost:11434"
JUDGE_MODEL = "qwen3:8b"

client = Client(host=OLLAMA_HOST)


@dataclass
class JudgeResult:
    faithfulness: float
    relevance: float
    citation_correctness: float
    claims: list[dict]


JUDGE_PROMPT = """
You are an evaluation judge for a Retrieval-Augmented Generation system.

Evaluate the answer ONLY against the provided policy sources.

Do not use outside knowledge.

You must evaluate:

1. Faithfulness:
   Are the factual claims in the answer supported by the sources?

2. Relevance:
   Does the answer directly answer the user's question?

3. Citation correctness:
   When the answer cites [Source N], does that source support the claim?

Return ONLY valid JSON.

Use this exact structure:

{
  "faithfulness": 0.0,
  "relevance": 0.0,
  "citation_correctness": 0.0,
  "claims": [
    {
      "claim": "short factual claim",
      "supported": true,
      "citation_correct": true
    }
  ]
}

Scoring:

faithfulness =
supported factual claims / total factual claims

relevance:
1.0 = directly answers the question
0.5 = partially answers
0.0 = does not answer

citation_correctness =
correctly supported citations / citations used

If there are no factual claims, faithfulness should be 1.0.

If there are no citations, citation_correctness should be 0.0 for an answer
that makes factual claims.

Do not reward information that is not present in the sources.
""".strip()


def judge_answer(
    question: str,
    answer: str,
    context: str,
    retries: int = 1,
) -> JudgeResult | None:

    user_prompt = f"""
QUESTION:
{question}

ANSWER:
{answer}

POLICY SOURCES:
{context}
""".strip()

    # The judge occasionally returns empty or malformed JSON;
    # retry, then give up so one bad case doesn't abort the run.
    for _ in range(retries + 1):
        response = client.chat(
            model=JUDGE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": JUDGE_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            options={
                "temperature": 0.0,
            },
            format="json",
            think=True,
        )

        raw = response["message"]["content"]

        try:
            data = json.loads(raw)

            return JudgeResult(
                faithfulness=float(data["faithfulness"]),
                relevance=float(data["relevance"]),
                citation_correctness=float(
                    data["citation_correctness"]
                ),
                claims=data.get("claims", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue

    return None