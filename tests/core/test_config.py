import pytest
from pydantic import ValidationError

import app.core.db
from app.core.config import InfraSettings

LOCAL_URL = "postgresql+psycopg://user:s3cret-pw@localhost:5433/policy_copilot"


def settings(**overrides):
    # _env_file=None: test the class itself, not whatever .env contains.
    return InfraSettings(_env_file=None, **overrides)


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("POLICY_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        settings()


def test_database_url_must_be_postgres():
    with pytest.raises(ValidationError):
        settings(database_url="sqlite:///x.db")


def test_password_never_appears_in_repr_or_dump():
    s = settings(database_url=LOCAL_URL)

    assert "s3cret-pw" not in repr(s)
    assert "s3cret-pw" not in s.model_dump_json()
    assert s.database_url.get_secret_value() == LOCAL_URL


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("POLICY_LLM_MODEL", "other-model")
    monkeypatch.setenv("POLICY_LLM_TIMEOUT_S", "30")

    s = settings(database_url=LOCAL_URL)

    assert s.llm_model == "other-model"
    assert s.llm_timeout_s == 30.0


def test_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        settings(database_url=LOCAL_URL, llm_timeout_s=0)


def test_tests_never_use_the_development_database():
    assert app.core.db.engine.url.database.endswith("_test")
