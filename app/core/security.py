from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.authz import ROLES
from app.core.config import get_settings
from app.core.observability import record

logger = logging.getLogger("policy_copilot.auth")

ADMIN_ROLE = "admin"
TOKEN_ROLES = ROLES | {ADMIN_ROLE}

bearer_schema = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    
    @property
    def document_roles(self) -> list[str]:
        return sorted(self.roles & ROLES)
    
    @property
    def is_admin(self) -> bool:
        return ADMIN_ROLE in self.roles


class AuthError(Exception):
    pass


def create_access_token(
    subject: str,
    roles: list[str],
    ttl_minutes: int | None = None,
) -> str:
    settings = get_settings()
    
    unknown = set(roles) - TOKEN_ROLES
    if unknown:
        raise ValueError(f"Unknown role(s): {', '.join(sorted(unknown))}")
    
    
    now = datetime.now(timezone.utc)
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_ttl_minutes
    
    payload = {
        "sub": subject,
        "roles": sorted(set(roles)),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
    }
    
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> Principal:
    settings = get_settings()
    
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    
    roles = claims.get("roles")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise AuthError("Token 'roles' claim must be a list of strings.")
    
    unknown = set(roles) - TOKEN_ROLES
    if unknown:
        raise AuthError(f"Unknown role(s) in token: {', '.join(sorted(unknown))}")
    
    return Principal(subject=claims["sub"], roles=frozenset(roles))


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token. ",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_schema)
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("auth_failed", extra={"reason": "missing_bearer_token"})
        raise _unauthorized()

    try:
        principal = decode_token(credentials.credentials)
    except AuthError as exc:
        # The reason comes from claim validation; the token is never logged.
        logger.warning("auth_failed", extra={"reason": str(exc)})
        raise _unauthorized()

    record(sub=principal.subject, roles=sorted(principal.roles))
    return principal


def require_admin(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    if not principal.is_admin:
        logger.warning("forbidden", extra={"required_role": ADMIN_ROLE})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return principal
