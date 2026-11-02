from app.lexical_retreival import retrieve_lexical


def test_lexical_retrieval(db):
    results = retrieve_lexical(
        db=db,
        query="annual leave",
        top_k=5,
    )

    assert len(results) > 0

    for result in results:
        assert result.chunk_id is not None
        assert result.score >= 0