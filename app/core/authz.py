from collections.abc import Iterable, Sequence
from sqlalchemy import exists
from app.core.models import Chunk, DocumentACL

ROLES = frozenset({"employee", "manager", "hr", "security"})
ALL_ROLES: tuple[str, ...] = tuple(sorted(ROLES))

def normalize_roles(roles: Iterable[str]) -> list[str]:
    cleaned = sorted({
        role.strip().lower()
        for role in roles
        if role and role.strip()
    })
    
    if not cleaned:
        raise ValueError("At least one roles is required")
    
    unknown = [role for role in cleaned if role not in ROLES]
    if unknown:
        raise ValueError(
            f"Unknown role(s): {', '.join(unknown)}. "
            f"Valid roles: {', '.join(sorted(ROLES))}."
        )

    return cleaned


def readable_by(roles: Sequence[str]):
    return exists().where(
        DocumentACL.document_id == Chunk.document_id,
        DocumentACL.role.in_(list(roles)),
        DocumentACL.permission == "read",
    )
