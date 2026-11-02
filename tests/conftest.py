import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base


TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "policy_user:policy_password@localhost:5433/policy_copilot_test"
)


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
