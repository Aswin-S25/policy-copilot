"""What produced a result: code version, retrieval configuration, models."""
import subprocess

from app.config import get_infra_settings
from app.search import CANDIDATE_K


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return None


def provenance() -> dict:
    settings = get_infra_settings()
    return {
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "retrieval": (
            f"hybrid RRF k=60, {CANDIDATE_K} dense + {CANDIDATE_K} lexical "
            f"candidates, top-5"
        ),
        "llm_model": settings.llm_model,
        "judge_model": settings.judge_model,
        "embedding_model": settings.embedding_model,
    }
