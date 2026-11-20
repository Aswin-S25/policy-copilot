from ingest.embeddings import embed_text, embed_texts


def test_embed_text():
    embedding = embed_text("Employees are entitled to annual leave.")

    assert len(embedding) == 384
    assert all(isinstance(value, float) for value in embedding)


def test_embed_texts():
    texts = [
        "Employees are entitled to annual leave.",
        "Employees must follow the security policy.",
    ]

    embeddings = embed_texts(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384
    assert len(embeddings[1]) == 384