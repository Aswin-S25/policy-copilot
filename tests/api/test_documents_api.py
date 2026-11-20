import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.api.documents as documents_api
from app.api.documents import document_status
from app.core.security import create_access_token
from app.main import app
from ingest.embed import embed_document_chunks
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document

client = TestClient(app)


def bearer(roles, sub="alice"):
    return {"Authorization": f"Bearer {create_access_token(sub, roles)}"}


def ingest(db, title, roles, embed=True):
    text = f"Policy text for {title}."
    document = ingest_document(
        db,
        ParsedDocument(
            title=title, source=f"data/policies/{title}.md", document_type="markdown", content=text,
            sections=[ParsedSection(title="Scope", level=2, content=text, position=0)],
        ),
        allowed_roles=roles,
    )
    if embed:
        embed_document_chunks(db, document.id)
    return document.id


@pytest.fixture
def library(db, monkeypatch):
    monkeypatch.setattr(documents_api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return {
        "handbook": ingest(db, "Employee Handbook", ["employee", "manager"]),
        "incident": ingest(db, "Incident Response", ["security"]),
        "pending": ingest(db, "Travel Policy", ["employee"], embed=False),
    }


def titles(response):
    return [d["title"] for d in response.json()["documents"]]


def test_requires_token():
    assert client.get("/documents").status_code == 401


def test_lists_only_readable_documents(library):
    response = client.get("/documents", headers=bearer(["employee"]))

    assert response.status_code == 200
    assert titles(response) == ["Employee Handbook", "Travel Policy"]


def test_access_lists_only_the_callers_granting_roles(library):
    documents = client.get("/documents", headers=bearer(["employee"])).json()["documents"]
    handbook = next(d for d in documents if d["title"] == "Employee Handbook")

    # The handbook is also readable by managers; an employee isn't told.
    assert handbook["access"] == ["employee"]


def test_metadata_and_status(library):
    documents = client.get("/documents", headers=bearer(["employee"])).json()["documents"]
    by_title = {d["title"]: d for d in documents}

    assert by_title["Employee Handbook"]["status"] == "ready"
    assert by_title["Travel Policy"]["status"] == "indexing"
    assert by_title["Employee Handbook"]["section_count"] == 1
    assert by_title["Employee Handbook"]["document_type"] == "markdown"
    assert "source" not in by_title["Employee Handbook"]  # server path stays private


def test_uploaded_file_names_are_shown_as_first_heading(db, library):
    ingest(db, "5f1c0e2a-upload", ["employee"])  # file-name title, first heading "Scope"

    assert "Scope" in titles(client.get("/documents", headers=bearer(["employee"])))
    assert "5f1c0e2a-upload" not in titles(client.get("/documents", headers=bearer(["employee"])))


def test_admin_without_document_role_sees_nothing(library):
    assert titles(client.get("/documents", headers=bearer(["admin"]))) == []


def test_document_status_rules():
    assert document_status(chunks=0, unembedded=0) == "empty"
    assert document_status(chunks=4, unembedded=1) == "indexing"
    assert document_status(chunks=4, unembedded=0) == "ready"
