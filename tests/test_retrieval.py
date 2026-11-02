from app.retrieval import retrieve_chunks


def test_retrieve_chunks(db):
    results = retrieve_chunks(
        db=db,
        query="annual leave",
        top_k=3,
    )

    assert len(results) <= 3

    for result in results:
        assert result.content
        assert 0.0 <= result.score <= 1.0