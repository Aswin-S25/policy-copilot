from eval.security_eval import (
    classify_access,
    fact_tokens,
    restricted_fingerprints,
)


def test_classify_access():
    assert classify_access({"a"}, {"a", "b"}) == "authorized"
    assert classify_access({"a"}, {"b"}) == "restricted"
    assert classify_access({"a", "b"}, {"b"}) == "partial"
    assert classify_access(set(), {"a"}) == "unanswerable"


def test_fact_tokens_extracts_identifiers_and_numbers():
    tokens = fact_tokens(
        "IR-SEV1 is acknowledged within 15 minutes; DCS-4 limit is 2.5 GB."
    )

    assert tokens == {"IR-SEV1", "15", "DCS-4", "2.5"}


def test_fingerprints_exclude_question_and_readable_corpus():
    fingerprints = restricted_fingerprints(
        question="How fast must IR-SEV1 be acknowledged?",
        restricted_texts=["IR-SEV1: acknowledge within 15 minutes, update every 30 minutes."],
        readable_tokens={"30"},  # appears in a document this role may read
    )

    # IR-SEV1 is in the question, 30 is readable elsewhere: only 15 is a
    # fact the role could only have learned from the restricted document.
    assert fingerprints == {"15"}
