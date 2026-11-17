import app.search as search_module
from app.search import CANDIDATE_K, search_policies


def test_search_policies_uses_hybrid_and_forwards_roles(monkeypatch):
    calls = []

    def fake_hybrid(**kwargs):
        calls.append(kwargs)
        return ["chunk-a"]

    monkeypatch.setattr(search_module, "retrieve_hybrid", fake_hybrid)

    result = search_policies(db=None, query="q", roles=["employee"], top_k=3)

    assert result == ["chunk-a"]
    assert calls == [{
        "db": None,
        "query": "q",
        "top_k": 3,
        "candidate_k": CANDIDATE_K,
        "roles": ["employee"],
    }]
