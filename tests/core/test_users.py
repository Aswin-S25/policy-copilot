import io

import pytest
from sqlalchemy.orm import sessionmaker

import app.cli.users as users_cli
from app.core.models import User
from app.core.users import (
    UserError,
    authenticate,
    create_user,
    normalize_username,
    set_password,
    validate_password,
    validate_roles,
)

PASSWORD = "correct horse battery"


def test_username_rules():
    assert normalize_username("  Alice.Smith ") == "alice.smith"
    for bad in ("ab", "-alice", "alice-", "al ice", "alice@corp", "a" * 65):
        with pytest.raises(UserError):
            normalize_username(bad)


def test_password_and_role_rules():
    with pytest.raises(UserError):
        validate_password("short")
    with pytest.raises(UserError):
        validate_password("x" * 257)
    assert validate_roles([" Manager", "employee", "employee"]) == ["employee", "manager"]
    assert validate_roles(["admin"]) == ["admin"]
    for bad in ([], ["superuser"]):
        with pytest.raises(UserError):
            validate_roles(bad)


def test_password_is_stored_hashed(db):
    user = create_user(db, "Alice", PASSWORD, ["employee"])

    assert user.username == "alice"
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")


def test_duplicate_username_is_rejected(db):
    create_user(db, "alice", PASSWORD, ["employee"])
    with pytest.raises(UserError, match="already exists"):
        create_user(db, "ALICE", PASSWORD, ["hr"])


def test_authenticate(db):
    create_user(db, "alice", PASSWORD, ["employee"])

    assert authenticate(db, "Alice", PASSWORD).username == "alice"  # case-insensitive username
    assert authenticate(db, "alice", "wrong password") is None
    assert authenticate(db, "nobody", PASSWORD) is None
    assert authenticate(db, "not a valid name!", PASSWORD) is None


def test_disabled_account_cannot_sign_in(db):
    user = create_user(db, "alice", PASSWORD, ["employee"])
    user.is_active = False

    assert authenticate(db, "alice", PASSWORD) is None


def test_password_change(db):
    user = create_user(db, "alice", PASSWORD, ["employee"])
    set_password(user, "a different passphrase")

    assert authenticate(db, "alice", PASSWORD) is None
    assert authenticate(db, "alice", "a different passphrase") is not None


@pytest.fixture
def cli(db, monkeypatch):
    monkeypatch.setattr(users_cli, "SessionLocal", sessionmaker(bind=db.get_bind()))

    def run(*argv, stdin=None):
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        return users_cli.run(list(argv))

    return run


def test_cli_manages_accounts(cli, db):
    assert cli("create", "alice", "--roles", "employee", "manager", "--password-stdin",
               stdin=PASSWORD + "\n") == "Created alice (employee, manager)."
    assert "alice" in cli("list")

    cli("set-roles", "alice", "--roles", "hr")
    cli("disable", "alice")
    db.expire_all()
    user = db.query(User).one()
    assert user.roles == ["hr"] and user.is_active is False

    assert cli("delete", "alice").startswith("Deleted alice")
    assert cli("list") == "No accounts yet."


def test_cli_reports_unknown_user(cli):
    with pytest.raises(UserError, match="No user named"):
        cli("disable", "ghost")
