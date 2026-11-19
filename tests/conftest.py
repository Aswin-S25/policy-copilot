import os

from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "POLICY_TEST_DATABASE_URL",
    "postgresql+psycopg://policy_user:policy_password@localhost:5433/policy_copilot_test",
)

# The db fixture runs drop_all: refuse anything that is not a test database.
if not make_url(TEST_DATABASE_URL).database.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against non-test database "
        f"{make_url(TEST_DATABASE_URL).database!r}"
    )

# Must run before any app module is imported: app.db builds its engine from
# settings at import time, so even SessionLocal points at the test database.
os.environ["POLICY_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("POLICY_JWT_SECRET", "test-secret-" + "x" * 40)
# Rate limits are exercised explicitly in tests/test_rate_limit.py; elsewhere
# they would make unrelated tests depend on how many requests ran before.
os.environ["POLICY_RATE_LIMIT_ENABLED"] = "false"
os.environ["POLICY_RATE_LIMIT_BACKEND"] = "memory"

import pytest  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import Base  # noqa: E402

@pytest.fixture
def db():
    engine = create_engine(TEST_DATABASE_URL)

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)

    session = Session()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
