"""Username/password sign-in.

Issues the same bearer token as app/cli/issue_token.py (create_access_token),
so every other endpoint is unchanged: the API still only verifies tokens.
Tokens are stateless; signing out discards the token on the client, and a
token stays valid until it expires (POLICY_JWT_TTL_MINUTES).
"""
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.observability import record
from app.core.rate_limit import check_login_attempt
from app.core.security import create_access_token
from app.core.users import MAX_PASSWORD_LENGTH, authenticate

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
