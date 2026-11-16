import pytest

from app.hybrid_retrieval import retrieve_hybrid
from app.lexical_retreival import retrieve_lexical
from app.retrieval import retrieve_chunks
from ingest.embed import embed_document_chunks
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document

PUBLIC_TEXT = "Employees receive 24 days of annual leave per year."
RESTRICTED_TEXT = (
    "Annual leave for incident responders: annual leave is frozen during a "
    "SEV1 incident, and annual leave requests need security approval."
)
UNASSIGNED_TEXT = "Annual leave draft rules pending approval."

RETRIEVERS = [retrieve_chunks, retrieve_lexical, retrieve_hybrid]
RETRIEVER_IDS = ["dense", "lexical", "hybrid"]


def make(title, source, section, text):
    return ParsedDocument(
        title=title,
        source=source,
        document_type="markdown",
        content=text,
        sections=[
            ParsedSection(title=section, level=2, content=text, position=0),
        ],
    )


@pytest.fixture
def corpus(db):
    public = ingest_document(
        db,
        make("Benefits Policy", "benefits.md", "Entitlement", PUBLIC_TEXT),
        allowed_roles=["employee", "security"],
    )
    restricted = ingest_document(
        db,
        make("Incident Response", "incident.md", "Responders", RESTRICTED_TEXT),
        allowed_roles=["security"],
    )
    # No allowed_roles: no ACL rows, so deny by default.
    unassigned = ingest_document(
        db,
        make("Draft Policy", "draft.md", "Draft", UNASSIGNED_TEXT),
    )

    for document in (public, restricted, unassigned):
        embed_document_chunks(db, document.id)

    return {
        "public": public.id,
        "restricted": restricted.id,
        "unassigned": unassigned.id,
    }


def search(retrieve, db, roles, query="annual leave", top_k=10):
    kwargs = {"min_score": 0.0} if retrieve is retrieve_chunks else {}
    return retrieve(db=db, query=query, top_k=top_k, roles=roles, **kwargs)


def document_ids(results):
    return {result.document_id for result in results}


@pytest.mark.parametrize("retrieve", RETRIEVERS, ids=RETRIEVER_IDS)
def test_employee_sees_only_authorized_documents(db, corpus, retrieve):
    results = search(retrieve, db, roles=["employee"])

    assert document_ids(results) == {corpus["public"]}


@pytest.mark.parametrize("retrieve", RETRIEVERS, ids=RETRIEVER_IDS)
def test_security_sees_restricted_but_not_unassigned(db, corpus, retrieve):
    results = search(retrieve, db, roles=["security"])

    assert document_ids(results) == {corpus["public"], corpus["restricted"]}


@pytest.mark.parametrize("retrieve", RETRIEVERS, ids=RETRIEVER_IDS)
def test_multiple_granting_roles_do_not_duplicate_chunks(db, corpus, retrieve):
    # The public document is granted to both roles; EXISTS must not
    # return its chunk twice (a JOIN would).
    results = search(retrieve, db, roles=["employee", "security"])
    chunk_ids = [result.chunk_id for result in results]

    assert len(chunk_ids) == len(set(chunk_ids))
    assert document_ids(results) == {corpus["public"], corpus["restricted"]}


@pytest.mark.parametrize("retrieve", RETRIEVERS, ids=RETRIEVER_IDS)
def test_no_roles_returns_nothing(db, corpus, retrieve):
    assert search(retrieve, db, roles=[]) == []


def test_unknown_role_returns_nothing(db, corpus):
    assert search(retrieve_lexical, db, roles=["admin"]) == []


def test_filter_applies_before_limit(db, corpus):
    # Precondition: for a user who can see both, the restricted chunk
    # outranks the public one.
    top_for_security = retrieve_lexical(
        db=db, query="annual leave", top_k=1, roles=["security"]
    )
    assert top_for_security[0].document_id == corpus["restricted"]

    # If filtering happened after LIMIT 1, the employee would get [].
    top_for_employee = retrieve_lexical(
        db=db, query="annual leave", top_k=1, roles=["employee"]
    )
    assert [r.document_id for r in top_for_employee] == [corpus["public"]]
