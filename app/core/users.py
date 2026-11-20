"""User accounts: validation, password hashing and authentication.

Passwords are hashed with Argon2id (argon2-cffi defaults, the RFC 9106
low-memory profile). Hashes are upgraded transparently at sign-in when
the parameters change.

authenticate() spends the same hashing work whether or not the username
exists, so response time does not reveal which accounts exist.
"""
import re
from collections.abc import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import User
from app.core.security import TOKEN_ROLES

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}[a-z0-9]$")
MIN_PASSWORD_LENGTH = 8
# Bounds hashing work per request; also the API's request field limit.
MAX_PASSWORD_LENGTH = 256

_hasher = PasswordHasher()
# Verified against when the account doesn't exist, to equalize timing.
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")


class UserError(ValueError):
    """Invalid input or a conflicting account; the message is user-facing."""


def normalize_username(username: str) -> str:
    name = username.strip().lower()
    if not USERNAME_RE.match(name):
        raise UserError(
            "Usernames are 3 to 64 characters: lowercase letters, digits, "
            "'.', '_' or '-', starting and ending with a letter or digit."
        )
    return name


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise UserError(f"Passwords can have at most {MAX_PASSWORD_LENGTH} characters.")
    return password


def validate_roles(roles: Iterable[str]) -> list[str]:
    cleaned = sorted({role.strip().lower() for role in roles if role and role.strip()})
    if not cleaned:
        raise UserError("At least one role is required.")
    unknown = set(cleaned) - TOKEN_ROLES
    if unknown:
        raise UserError(
            f"Unknown role(s): {', '.join(sorted(unknown))}. "
            f"Valid roles: {', '.join(sorted(TOKEN_ROLES))}."
        )
    return cleaned


def hash_password(password: str) -> str:
    return _hasher.hash(validate_password(password))


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def get_user(db: Session, username: str) -> User | None:
    try:
        name = normalize_username(username)
    except UserError:
        return None
    return db.scalar(select(User).where(User.username == name))


def create_user(db: Session, username: str, password: str, roles: Iterable[str]) -> User:
    name = normalize_username(username)
    if get_user(db, name) is not None:
        raise UserError(f"A user named {name!r} already exists.")
    user = User(username=name, password_hash=hash_password(password), roles=validate_roles(roles))
    db.add(user)
    db.flush()
    return user


def set_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)


def authenticate(db: Session, username: str, password: str) -> User | None:
    """The active user with this username and password, or None.

    Unknown, inactive and wrong-password cases are indistinguishable to the
    caller and take the same hashing time.
    """
    user = get_user(db, username) if len(password) <= MAX_PASSWORD_LENGTH else None
    if user is None or not user.is_active:
        _verify(_DUMMY_HASH, password[:MAX_PASSWORD_LENGTH])
        return None
    if not _verify(user.password_hash, password):
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
    return user
