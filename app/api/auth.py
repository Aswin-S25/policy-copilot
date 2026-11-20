"""Sign-in: username/password, and optional one-click demo sessions.

Issues the same bearer token as app/cli/issue_token.py (create_access_token),
so every other endpoint is unchanged: the API still only verifies tokens.
Tokens are stateless; signing out discards the token on the client, and a
token stays valid until it expires (POLICY_JWT_TTL_MINUTES).

Demo mode (POLICY_DEMO_MODE=true) lets anyone sign in as a sample persona.
Each demo sign-in gets a fresh subject ("demo-<persona>-<random>"), so
visitors never see each other's conversations, and no real account can
have that prefix (app/core/users.py).
"""
import logging
import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.documents import readable_documents_query
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.observability import record
from app.core.rate_limit import check_login_attempt
from app.core.security import create_access_token
from app.core.users import DEMO_PREFIX, MAX_PASSWORD_LENGTH, authenticate

logger = logging.getLogger("policy_copilot.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


@router.post("/login")
def login(credentials: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    check_login_attempt(credentials.username.strip().lower(), client_ip)

    with SessionLocal() as db:
        user = authenticate(db, credentials.username, credentials.password)
        if user is None:
            # One message for unknown user, wrong password and disabled
            # account. Neither the username nor the password is logged.
            logger.warning("login_failed")
            record(login="failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password.",
            )
        subject, roles = user.username, list(user.roles)
        db.commit()  # persists a transparent password-hash upgrade, if any

    record(sub=subject, roles=sorted(roles), login="succeeded")
    return {
        "access_token": create_access_token(subject, roles),
        "token_type": "bearer",
        "expires_in": get_settings().jwt_ttl_minutes * 60,
    }


# ---- demo sessions ---------------------------------------------------------------

# Each persona adds one specialist role to "employee", so a demo shows the
# same question answered from different sets of documents.
DEMO_PERSONAS: dict[str, dict] = {
    "employee": {"label": "Employee", "roles": ["employee"]},
    "manager": {"label": "Manager", "roles": ["employee", "manager"]},
    "hr": {"label": "HR", "roles": ["employee", "hr"]},
    "security": {"label": "Security", "roles": ["employee", "security"]},
}


def demo_mode_enabled() -> bool:
    return get_settings().demo_mode


def _readable_document_count(db, roles: list[str]) -> int:
    return db.scalar(select(func.count()).select_from(readable_documents_query(roles).subquery()))


@router.get("/options")
def sign_in_options():
    """Public: what the sign-in page should offer. Demo personas, with how
    many documents each can read, only when demo mode is on."""
    if not demo_mode_enabled():
        return {"demo": None}
    with SessionLocal() as db:
        personas = [
            {
                "id": persona_id,
                "label": persona["label"],
                "roles": persona["roles"],
                "document_count": _readable_document_count(db, persona["roles"]),
            }
            for persona_id, persona in DEMO_PERSONAS.items()
        ]
    return {"demo": {"personas": personas}}


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona: Literal["employee", "manager", "hr", "security"]


@router.post("/demo")
def demo_sign_in(body: DemoRequest, request: Request):
    if not demo_mode_enabled():
        # As if the route didn't exist: nothing to discover when it's off.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    client_ip = request.client.host if request.client else "unknown"
    # Per-address budget only (a per-persona one would be shared by every
    # visitor): fresh demo identities must not become a way around the
    # per-user question limits.
    check_login_attempt(None, client_ip)

    persona = DEMO_PERSONAS[body.persona]
    subject = f"{DEMO_PREFIX}{body.persona}-{secrets.token_hex(4)}"
    record(sub=subject, roles=persona["roles"], login="demo")
    return {
        "access_token": create_access_token(subject, persona["roles"]),
        "token_type": "bearer",
        "expires_in": get_settings().jwt_ttl_minutes * 60,
    }
