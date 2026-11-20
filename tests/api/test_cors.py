"""CORS is configured at import time from POLICY_CORS_ORIGINS, so these tests
build a fresh app the same way app/main.py does."""
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import InfraSettings

ORIGIN = "https://policy-copilot.vercel.app"


def app_with(origins: list[str]) -> TestClient:
    app = FastAPI()

    @app.get("/thing")
    def thing():
        return {"ok": True}

    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["Retry-After", "X-Request-ID"], max_age=600,
        )
    return TestClient(app)


def settings(**values):
    values.setdefault("database_url", "postgresql://u:p@h/db")
    return InfraSettings(_env_file=None, **values)


def test_origin_list_parsing():
    assert settings(cors_origins="").cors_origin_list == []
    assert settings(cors_origins=f" {ORIGIN}/ , http://localhost:5173").cors_origin_list == [
        ORIGIN, "http://localhost:5173",
    ]


def test_allowed_origin_gets_preflight_and_exposed_headers():
    client = app_with([ORIGIN])
    preflight = client.options("/thing", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN

    response = client.get("/thing", headers={"Origin": ORIGIN})
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "Retry-After" in response.headers["access-control-expose-headers"]
    assert "access-control-allow-credentials" not in response.headers


def test_other_origins_get_no_cors_headers():
    response = app_with([ORIGIN]).get("/thing", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_provider_settings_must_be_complete():
    with pytest.raises(ValueError, match="POLICY_LLM_BASE_URL"):
        settings(llm_provider="openai")
    with pytest.raises(ValueError, match="POLICY_EMBEDDING_ONNX_DIR"):
        settings(embedding_backend="onnx")
    assert settings(llm_provider="openai", llm_base_url="https://api.groq.com/openai/v1").llm_provider == "openai"


def test_hosted_postgres_urls_use_psycopg3():
    for given in ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require", "postgres://u:p@h/db"):
        url = settings(database_url=given).database_url.get_secret_value()
        assert url.startswith("postgresql+psycopg://")
    kept = "postgresql+psycopg://u:p@127.0.0.1:5433/db"
    assert settings(database_url=kept).database_url.get_secret_value() == kept
    with pytest.raises(ValueError):
        settings(database_url="mysql://u:p@h/db")
