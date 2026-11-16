import uuid
from collections.abc import Iterable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.authz import normalize_roles
from app.models import DocumentACL

def replace_document_acl(
    db: Session,
    document_id: uuid.UUID,
    roles: Iterable[str],
) -> list[str]:
    
    normalized = normalize_roles(roles)
    
    db.execute(
        delete(DocumentACL).where(
            DocumentACL.document_id == document_id
        )
    )
    
    db.add_all(
        DocumentACL(
            document_id = document_id,
            role = role,
            permission="read",
        )
        for role in normalized
    )
    
    db.flush()
    
    return normalized