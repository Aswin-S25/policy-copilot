import argparse
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Document, DocumentACL
from ingest.acl import replace_document_acl


ALL_ROLES = ["employee", "manager", "hr", "security"]

POLICY_ACL = {
    "Employee Policy Handbook": ALL_ROLES,
    "Remote and Hybrid Work Policy": ALL_ROLES,
    "Wellbeing and Benefits Policy": ALL_ROLES,
    "Learning and Development Policy": ALL_ROLES,
    "Anti-Harassment and Grievance Policy": ALL_ROLES,
    "IT Asset Management Policy": ALL_ROLES,
    "Information Security Standard": ALL_ROLES,
    "Onboarding and Probation Policy": ["manager", "hr"],
    "Incident Response Procedure": ["security"],
    "Data Classification Standard": ["security"],
}


def h1_header(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        documents = db.scalars(
            select(Document).order_by(Document.source)
        ).all()
        
        matched_headings = set()
        unmatched = []
        
        for document in documents:
            heading = h1_header(document.source)
            roles = POLICY_ACL.get(heading)
            
            if roles is None:
                unmatched.append((document.id, document.source, heading))
                continue
            
            matched_headings.add(heading)
            print(f"{heading:<40} -> {', '.join(roles)}")
            
            if apply:
                replace_document_acl(db, document.id, roles)
                
        for document_id, source, heading in unmatched:
            print(f"WARNING no ACL (deny by default): {document_id} {source} heading={heading!r}")
            
        for heading in sorted(set(POLICY_ACL) - matched_headings):
            print(f"WARNING mapping not used, no document found: {heading!r}")
        
        
        if apply:
            db.commit()
            rows = db.execute(
                select(DocumentACL.role, func.count())
                .group_by(DocumentACL.role)
                .order_by(DocumentACL.role)
            ).all()
            print("\nACL rows per role:")
            for role, count in rows:
                print(f"   {role:<10} {count}")
        else:
            print("\nDry run: nothing written. Re-run with --apply.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    main(parser.parse_args().apply)