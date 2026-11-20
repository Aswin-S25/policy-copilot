from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.security import (
    AuthError,
    Principal,
    create_access_token,
    decode_token,
)

client = TestClient(app)

READ_ENDPOINTS = [
    ("post", "/search", {"query": "annual leave"}),
    ("post", "/talk", {"question": "annual leave"}),
    ("post", "/ask/stream", {"question": "annual leave"}),
]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def forged(key=None, algorithm="HS256", **overrides):
    """Build a token by hand so each claim can be broken individually."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "mallory",
        "roles": ["employee"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    if key is None and algorithm != "none":
        key = settings.jwt_secret.get_secret_value()
    return jwt.encode(claims, key, algorithm=algorithm)


# ---- authentication: 401 ------------------------------------------------

@pytest.mark.parametrize("method,path,body", READ_ENDPOINTS)
def test_read_endpoints_require_token(method, path, body):
    response = client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_admin_endpoints_require_token():
    assert client.get("/task/some-id").status_code == 401
    assert client.post(
        "/documents/ingest",
        files={"file": ("x.md", b"# X", "text/markdown")},
        data={"allowed_roles": "employee"},
    ).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(forged(key="wrong-secret-" + "y" * 40), id="bad-signature"),
        pytest.param(
            forged(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
            id="expired",
        ),
        pytest.param(forged(aud="some-other-api"), id="wrong-audience"),
        pytest.param(forged(iss="evil-issuer"), id="wrong-issuer"),
        pytest.param(forged(algorithm="none"), id="alg-none"),
        pytest.param(forged(roles=["superuser"]), id="unknown-role"),
        pytest.param(forged(roles="employee"), id="roles-not-a-list"),
        pytest.param(forged(sub=None), id="missing-sub"),
        pytest.param(forged(exp=None), id="missing-exp"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_invalid_tokens_rejected(token):
    with pytest.raises(AuthError):
        decode_token(token)

    response = client.post(
        "/search", json={"query": "annual leave"}, headers=bearer(token)
    )
    assert response.status_code == 401


# ---- authorization: 403 / 422 -------------------------------------------

def test_non_admin_cannot_upload_or_read_tasks():
    token = create_access_token("alice", ["employee", "security"])

    assert client.get("/task/some-id", headers=bearer(token)).status_code == 403
    assert client.post(
        "/documents/ingest",
        files={"file": ("x.md", b"# X", "text/markdown")},
        data={"allowed_roles": "employee"},
        headers=bearer(token),
    ).status_code == 403


def test_admin_upload_still_validates_document_roles():
    # Passes authentication and authorization, then fails role validation
    # before anything is written or queued.
    token = create_access_token("ops", ["admin"])

    response = client.post(
        "/documents/ingest",
        files={"file": ("x.md", b"# X", "text/markdown")},
        data={"allowed_roles": "superuser"},
        headers=bearer(token),
    )
    assert response.status_code == 400


@pytest.mark.parametrize("method,path,body", READ_ENDPOINTS)
def test_roles_in_request_body_are_rejected(method, path, body):
    token = create_access_token("alice", ["employee"])

    response = client.request(
        method,
        path,
        json={**body, "roles": ["security"]},
        headers=bearer(token),
    )
    assert response.status_code == 422


# ---- principal ------------------------------------------------------------

def test_valid_token_round_trip():
    principal = decode_token(create_access_token("bob", ["security", "employee"]))

    assert principal.subject == "bob"
    assert principal.document_roles == ["employee", "security"]
    assert not principal.is_admin


def test_admin_role_never_reaches_retrieval():
    principal = Principal(subject="ops", roles=frozenset({"admin"}))

    assert principal.is_admin
    assert principal.document_roles == []


def test_cannot_mint_token_with_unknown_role():
    with pytest.raises(ValueError):
        create_access_token("alice", ["superuser"])


# ---- roles flow from the token into retrieval ----------------------------

def test_stream_retrieves_with_token_document_roles_only(monkeypatch):
    import app.main as api
    import app.rag.pipeline as rag

    seen = {}

    def fake_search(**kwargs):
        seen.update(kwargs)
        return []  # no context: refused without calling the LLM

    monkeypatch.setattr(api, "search_policies", fake_search)
    monkeypatch.setattr(
        rag, "stream_answer",
        lambda **_: (_ for _ in ()).throw(AssertionError("LLM called")),
    )

    token = create_access_token("ops", ["admin", "employee"])
    response = client.post(
        "/ask/stream", json={"question": "annual leave"}, headers=bearer(token)
    )

    assert response.status_code == 200
    # "admin" never reaches retrieval; only document roles do.
    assert seen["roles"] == ["employee"]
    assert "event: answer" in response.text
    assert response.text.rstrip().endswith("data: {}")  # final "done" event


def test_min_score_is_no_longer_accepted():
    token = create_access_token("alice", ["employee"])

    response = client.post(
        "/talk",
        json={"question": "q", "min_score": 0.0},
        headers=bearer(token),
    )
    assert response.status_code == 422
