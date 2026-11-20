import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import app.api.sources as sources_api
from app.core.models import Chunk
from app.core.security import create_access_token
from app.main import app
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document

client = TestClient(app)

PUBLIC = "Employees receive 24 days of annual leave per year."
RESTRICTED = "SEV1 incidents must be acknowledged within 15 minutes by the on-call engineer."


def bearer(roles, sub="alice"):
    return {"Authorization": f"Bearer {create_access_token(sub, roles)}"}


def ingest(db, source, text, roles):
    document = ingest_document(
        db,
        ParsedDocument(
            title=source, source=source, document_type="markdown", content=text,
            sections=[ParsedSection(title="S", level=2, content=text, position=0)],
        ),
        allowed_roles=roles,
    )
    return db.scalars(select(Chunk.id).where(Chunk.document_id == document.id)).first()


@pytest.fixture
def chunks(db, monkeypatch):
    monkeypatch.setattr(sources_api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return {
        "public": ingest(db, "leave.md", PUBLIC, ["employee", "security"]),
        "restricted": ingest(db, "ir.md", RESTRICTED, ["security"]),
    }


def test_requires_token():
    assert client.get(f"/chunks/{uuid.uuid4()}").status_code == 401


def test_returns_readable_passage(chunks):
    response = client.get(f"/chunks/{chunks['public']}", headers=bearer(["employee"]))

    assert response.status_code == 200
    body = response.json()
    assert body["chunk_id"] == str(chunks["public"])
    assert body["document_title"] == "S"  # first heading, not the file name "leave.md"
    assert body["section_path"] == "S"
    assert PUBLIC in body["content"]


def test_unreadable_and_missing_chunks_look_the_same(chunks):
    forbidden = client.get(f"/chunks/{chunks['restricted']}", headers=bearer(["employee"]))
    missing = client.get(f"/chunks/{uuid.uuid4()}", headers=bearer(["employee"]))

    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json() == {"detail": "Source not found."}


def test_role_that_grants_access_can_read(chunks):
    response = client.get(f"/chunks/{chunks['restricted']}", headers=bearer(["security"]))
    assert response.status_code == 200
    assert RESTRICTED in response.json()["content"]


def test_admin_without_document_role_reads_nothing(chunks):
    response = client.get(f"/chunks/{chunks['public']}", headers=bearer(["admin"]))
    assert response.status_code == 404


def test_invalid_id_is_rejected(chunks):
    response = client.get("/chunks/not-a-uuid", headers=bearer(["employee"]))
    assert response.status_code == 422
