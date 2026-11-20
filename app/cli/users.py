"""Manage sign-in accounts.

    python -m app.cli.users create alice --roles employee manager
    python -m app.cli.users set-password alice
    python -m app.cli.users set-roles alice --roles employee hr
    python -m app.cli.users disable alice        # blocks sign-in; keeps the account
    python -m app.cli.users enable alice
    python -m app.cli.users delete alice
    python -m app.cli.users list

Passwords are read from a hidden prompt (asked twice), or from standard
input with --password-stdin for scripts. They are never accepted as a
command-line argument, which would leave them in shell history.

Disabling or changing roles affects the next sign-in; a token already
issued stays valid until it expires (POLICY_JWT_TTL_MINUTES).
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import User
from app.core.users import UserError, create_user, get_user, set_password, validate_password, validate_roles


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return validate_password(sys.stdin.readline().rstrip("\r\n"))
    first = getpass.getpass("Password: ")
    validate_password(first)
    if getpass.getpass("Repeat password: ") != first:
        raise UserError("The passwords don't match.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.users", description="Manage sign-in accounts.")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create an account")
    create.add_argument("username")
    create.add_argument("--roles", nargs="+", required=True)
    create.add_argument("--password-stdin", action="store_true")

    password = commands.add_parser("set-password", help="replace an account's password")
    password.add_argument("username")
    password.add_argument("--password-stdin", action="store_true")

    roles = commands.add_parser("set-roles", help="replace an account's roles")
    roles.add_argument("username")
    roles.add_argument("--roles", nargs="+", required=True)

    for name, text in (("disable", "block sign-in"), ("enable", "allow sign-in"), ("delete", "delete an account")):
        command = commands.add_parser(name, help=text)
        command.add_argument("username")

    commands.add_parser("list", help="list accounts")
    return parser


def run(argv: list[str] | None = None) -> str:
    """Executes one command and returns the message to print."""
    args = build_parser().parse_args(argv)

    with SessionLocal() as db:
        if args.command == "list":
            users = db.scalars(select(User).order_by(User.username)).all()
            if not users:
                return "No accounts yet."
            return "\n".join(
                f"{u.username:<24} {', '.join(u.roles):<32} {'active' if u.is_active else 'disabled'}"
                for u in users
            )

        if args.command == "create":
            roles = validate_roles(args.roles)
            user = create_user(db, args.username, read_password(args.password_stdin), roles)
            db.commit()
            return f"Created {user.username} ({', '.join(user.roles)})."

        user = get_user(db, args.username)
        if user is None:
            raise UserError(f"No user named {args.username.strip().lower()!r}.")

        if args.command == "set-password":
            set_password(user, read_password(args.password_stdin))
            message = f"Password changed for {user.username}."
        elif args.command == "set-roles":
            user.roles = validate_roles(args.roles)
            message = f"Roles for {user.username}: {', '.join(user.roles)}."
        elif args.command in ("disable", "enable"):
            user.is_active = args.command == "enable"
            message = f"{user.username} is now {'active' if user.is_active else 'disabled'}."
        else:  # delete
            db.delete(user)
            message = f"Deleted {user.username}. Their conversations are kept."
        db.commit()
        return message


def main() -> None:
    try:
        print(run())
    except UserError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
