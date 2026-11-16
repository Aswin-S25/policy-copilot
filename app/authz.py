from collections.abc import Iterable

ROLES = frozenset({"employee", "manager", "hr", "security"})

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