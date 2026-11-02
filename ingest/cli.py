import argparse

from app.db import SessionLocal
from ingest.parse import parse_markdown
from ingest.upsert import ingest_document


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
        help="Path to markdown document",
    )

    args = parser.parse_args()

    parsed = parse_markdown(args.file)

    db = SessionLocal()

    try:
        document = ingest_document(
            db,
            parsed,
        )

        print(
            f"Ingested: {document.title}"
        )

        print(
            f"Document ID: {document.id}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()