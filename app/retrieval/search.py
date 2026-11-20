"""The application's single retrieval entry point.

Every user-facing path (/search, /talk, /ask/stream) retrieves through
search_policies(), so the retrieval strategy is decided in exactly one place.

Decision record (Phase 7 step 3b, eval/experiments/compare_gating.py, 138 golden cases):
- Hybrid (RRF over dense + lexical) replaces dense: refusal accuracy
  0.971 vs 0.964, answerable questions answered 120/124 vs 118/123,
  unanswerable refused 14/14 for both, faithfulness 0.996 for both.
- No score-based answerability gate: best dense cosine of unanswerable
  questions (0.57-0.79) overlaps answerable ones (0.62-0.92), so no
  threshold separates them. Refusal is left to the grounded prompt and
  the citation check in app/rag/pipeline.py.
"""
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.retrieval.hybrid import retrieve_hybrid
from app.core.observability import record, stage
from app.retrieval.dense import RetrievedChunk

DEFAULT_TOP_K = 5
CANDIDATE_K = 20


def search_policies(
    db: Session,
    query: str,
    *,
    roles: Sequence[str],
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedChunk]:
    # Authorization is enforced inside dense and lexical SQL; roles must
    # come from the authenticated principal, never from the request.
    with stage("retrieval"):
        chunks = retrieve_hybrid(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=CANDIDATE_K,
            roles=roles,
        )
    record(retrieved=len(chunks))
    return chunks
