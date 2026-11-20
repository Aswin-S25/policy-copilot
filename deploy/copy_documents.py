"""Copy the policy knowledge base from one database to another.

    python deploy/copy_documents.py            # prompts for both URLs
    python deploy/copy_documents.py --dry-run  # checks only; writes nothing

Copies documents, sections, chunks (with their embeddings and full-text
vectors) and document_acl, exactly: same ids, same access rules, same
vectors. Nothing else: no users, no conversations.

Safety rules (the script refuses rather than guesses):
- Both databases must be at the same Alembic revision. Migrate the target
  first:  POLICY_DATABASE_URL=<target> alembic upgrade head
- The target tables must be empty. Nothing is ever overwritten or deleted.
- Everything is copied in one transaction; on any error nothing is written.

URLs are read from SOURCE_DATABASE_URL / TARGET_DATABASE_URL, or prompted
for without echo, so passwords don't end up in shell history.
"""
import argparse
import getpass
import os
import sys

import psycopg

# Parents before children (foreign keys).
TABLES = ("documents", "sections", "chunks", "document_acl")


def libpq_url(url: str) -> str:
    """SQLAlchemy-style URLs ("postgresql+psycopg://") to plain libpq ones."""
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def read_url(variable: str, label: str) -> str:
    url = os.environ.get(variable) or getpass.getpass(f"{label} database URL: ")
    if not url.strip():
        sys.exit(f"Error: no {label.lower()} database URL given.")
    return libpq_url(url.strip())


def host_of(url: str) -> str:
    return url.rsplit("@", 1)[-1].split("/", 1)[0]  # never print credentials


def revision(conn: psycopg.Connection) -> str | None:
    try:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return None


def columns(conn: psycopg.Connection, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    return [row[0] for row in rows]


def count(conn: psycopg.Connection, table: str) -> int:
    return conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="check both databases; copy nothing")
    args = parser.parse_args()

    source_url = read_url("SOURCE_DATABASE_URL", "Source")
    target_url = read_url("TARGET_DATABASE_URL", "Target")
    if host_of(source_url) == host_of(target_url) and source_url == target_url:
        sys.exit("Error: source and target are the same database.")

    with psycopg.connect(source_url) as source, psycopg.connect(target_url) as target:
        print(f"Source: {host_of(source_url)}   Target: {host_of(target_url)}")

        source_rev, target_rev = revision(source), revision(target)
        if source_rev is None or source_rev != target_rev:
            sys.exit(
                f"Error: schema revisions differ (source {source_rev}, target {target_rev}). "
                "Run 'alembic upgrade head' against the target first."
            )

        source_counts = {table: count(source, table) for table in TABLES}
        occupied = {table: n for table in TABLES if (n := count(target, table))}
        for table in TABLES:
            if columns(source, table) != columns(target, table):
                sys.exit(f"Error: table {table!r} has different columns in the two databases.")
        print("Rows to copy: " + ", ".join(f"{t} {n}" for t, n in source_counts.items()))
        if occupied:
            sys.exit(
                "Error: the target already has data in "
                + ", ".join(f"{t} ({n} rows)" for t, n in occupied.items())
                + ". This script never overwrites; nothing was changed."
            )
        if args.dry_run:
            print("Dry run: both databases are compatible. Nothing was copied.")
            return

        # One transaction on the target: all tables or none.
        with target.transaction():
            for table in TABLES:
                cols = ", ".join(f'"{c}"' for c in columns(source, table))
                with source.cursor().copy(f'COPY (SELECT {cols} FROM "{table}") TO STDOUT (FORMAT BINARY)') as out, \
                        target.cursor().copy(f'COPY "{table}" ({cols}) FROM STDIN (FORMAT BINARY)') as into:
                    for block in out:
                        into.write(block)
            copied = {table: count(target, table) for table in TABLES}
            if copied != source_counts:
                raise RuntimeError(f"row counts differ after copy: {copied} vs {source_counts}")

        print("Copied: " + ", ".join(f"{t} {n}" for t, n in copied.items()))


if __name__ == "__main__":
    main()
