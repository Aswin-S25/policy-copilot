from sqlalchemy import UniqueConstraint

from app.db import Base
from app import models  # noqa: F401  (registers tables on Base.metadata)


def _unique_constraints(table_name):
    table = Base.metadata.tables[table_name]
    return {
        c.name: tuple(col.name for col in c.columns)
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }


def test_models_exist():
    tables = Base.metadata.tables
    for name in ("documents", "sections", "chunks", "document_acl"):
        assert name in tables


def test_chunk_has_document_constraint():
    constraints = _unique_constraints("chunks")
    assert constraints.get("uq_document_chunk_index") == (
        "document_id",
        "chunk_index",
    )


def test_acl_has_document_role_constraint():
    constraints = _unique_constraints("document_acl")
    assert constraints.get("uq_document_role") == ("document_id", "role")
