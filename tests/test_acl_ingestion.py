import pytest
from sqlalchemy import func, select

from app.authz import normalize_roles
from app.models import Document, DocumentACL
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document


def make_document(content="Employees receive 12 days of leave."):
    return ParsedDocument(
        title="ACL Test Policy",
        source="acl_test_policy.md",
        document_type="markdown",
        content=content,
        sections=[
            ParsedSection(
                title="Leave",
                level=2,
                content=content,
                position=0,
            ),
        ],
    )


def acl_roles(db, document_id):
    return sorted(
        db.scalars(
            select(DocumentACL.role).where(
                DocumentACL.document_id == document_id
            )
        )
    )


def test_new_document_gets_requested_roles(db):
    document = ingest_document(
        db, make_document(), allowed_roles=["manager", "hr"]
    )

    assert acl_roles(db, document.id) == ["hr", "manager"]


def test_document_without_roles_has_no_acl(db):
    # Deny by default: no ACL rows means no role can read it.
    document = ingest_document(db, make_document())

    assert acl_roles(db, document.id) == []


def test_unchanged_content_still_updates_acl(db):
    parsed = make_document()
    document = ingest_document(db, parsed, allowed_roles=["employee"])

    # Same content, new permissions: the skip path must not ignore them.
    ingest_document(db, parsed, allowed_roles=["security"])

    assert acl_roles(db, document.id) == ["security"]


def test_changed_content_replaces_acl(db):
    document = ingest_document(
        db, make_document("Version one."), allowed_roles=["employee"]
    )

    ingest_document(
        db, make_document("Version two."), allowed_roles=["hr", "manager"]
    )

    assert acl_roles(db, document.id) == ["hr", "manager"]


def test_none_keeps_existing_acl(db):
    document = ingest_document(
        db, make_document("Version one."), allowed_roles=["hr"]
    )

    ingest_document(db, make_document("Version two."))

    assert acl_roles(db, document.id) == ["hr"]


def test_unknown_role_rejected_before_any_write(db):
    with pytest.raises(ValueError, match="Unknown role"):
        ingest_document(db, make_document(), allowed_roles=["admin"])

    assert db.scalar(select(func.count()).select_from(Document)) == 0


def test_normalize_roles():
    assert normalize_roles([" HR", "hr", "Manager"]) == ["hr", "manager"]

    with pytest.raises(ValueError):
        normalize_roles([])

    with pytest.raises(ValueError):
        normalize_roles(["", "  "])
