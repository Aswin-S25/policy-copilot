import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.api.auth as auth_api
import app.core.rate_limit as rate_limit
from app.core.config import Settings
from app.core.rate_limit import MemoryBackend, RateLimiter
from app.core.security import decode_token
from app.core.users import create_user
from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery"


@pytest.fixture
def accounts(db, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", sessionmaker(bind=db.get_bind()))
    create_user(db, "alice", PASSWORD, ["employee", "manager"])
    disabled = create_user(db, "mallory", PASSWORD, ["employee"])
    disabled.is_active = False
    db.commit()


def login(username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_valid_credentials_return_a_working_token(accounts):
    response = login("Alice", PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    principal = decode_token(body["access_token"])
    assert principal.subject == "alice"
    assert principal.roles == frozenset({"employee", "manager"})

    # The token is accepted by the rest of the API like any other.
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/conversations", headers=headers).status_code == 200


def test_failures_are_indistinguishable(accounts):
    wrong_password = login("alice", "not the password")
    unknown_user = login("nobody", PASSWORD)
    disabled_user = login("mallory", PASSWORD)

    for response in (wrong_password, unknown_user, disabled_user):
        assert response.status_code == 401
        assert response.json() == {"detail": "Incorrect username or password."}


def test_request_validation(accounts):
    assert client.post("/auth/login", json={"username": "alice"}).status_code == 422
    assert client.post("/auth/login", json={
        "username": "alice", "password": PASSWORD, "roles": ["admin"],
    }).status_code == 422  # can't ask for roles
    assert login("alice", "x" * 257).status_code == 422


def test_attempts_are_rate_limited_per_account(accounts, monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", RateLimiter(
        MemoryBackend(), limits={"llm": 99, "search": 99, "login_user": 2, "login_ip": 99},
    ))

    assert login("alice", "guess one").status_code == 401
    assert login("alice", "guess two").status_code == 401
    blocked = login("alice", PASSWORD)  # right password, but the budget is spent

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert login("nobody", "x").status_code == 401  # other accounts unaffected


def test_attempts_are_rate_limited_per_client(accounts, monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", RateLimiter(
        MemoryBackend(), limits={"llm": 99, "search": 99, "login_user": 99, "login_ip": 2},
    ))

    login("user-one", "x")
    login("user-two", "x")
    assert login("alice", PASSWORD).status_code == 429  # spraying across accounts


# ---- demo sessions ------------------------------------------------------------------

@pytest.fixture
def demo(db, monkeypatch, accounts):
    monkeypatch.setattr(auth_api, "demo_mode_enabled", lambda: True)


def test_demo_mode_defaults_to_off():
    # Independent of any local .env.
    settings = Settings(jwt_secret="x" * 40, _env_file=None)
    assert settings.demo_mode is False


def test_demo_endpoints_are_hidden_when_off(accounts, monkeypatch):
    monkeypatch.setattr(auth_api, "demo_mode_enabled", lambda: False)

    assert client.get("/auth/options").json() == {"demo": None}
    assert client.post("/auth/demo", json={"persona": "employee"}).status_code == 404


def test_options_list_personas_with_document_counts(demo):
    personas = client.get("/auth/options").json()["demo"]["personas"]

    assert [p["id"] for p in personas] == ["employee", "manager", "hr", "security"]
    assert all(p["roles"][0] == "employee" for p in personas)
    assert all(isinstance(p["document_count"], int) for p in personas)


def test_demo_sign_in_issues_a_private_identity_with_persona_roles(demo):
    first = client.post("/auth/demo", json={"persona": "security"}).json()
    second = client.post("/auth/demo", json={"persona": "security"}).json()

    one, two = decode_token(first["access_token"]), decode_token(second["access_token"])
    assert one.roles == frozenset({"employee", "security"})
    assert one.subject.startswith("demo-security-")
    assert one.subject != two.subject  # visitors don't share conversations


def test_demo_cannot_request_other_roles(demo):
    assert client.post("/auth/demo", json={"persona": "admin"}).status_code == 422
    assert client.post("/auth/demo", json={"persona": "employee", "roles": ["admin"]}).status_code == 422


def test_demo_sign_ins_are_rate_limited_per_client_not_per_persona(demo, monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", RateLimiter(
        MemoryBackend(), limits={"llm": 99, "search": 99, "login_user": 1, "login_ip": 2},
    ))

    # login_user=1 doesn't apply: different visitors share a persona.
    assert client.post("/auth/demo", json={"persona": "employee"}).status_code == 200
    assert client.post("/auth/demo", json={"persona": "employee"}).status_code == 200
    assert client.post("/auth/demo", json={"persona": "hr"}).status_code == 429
