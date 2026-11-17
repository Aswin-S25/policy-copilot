"""DEV ONLY: mint a JWT for local testing.

In production an identity provider issues tokens; this API only verifies them.

    python -m app.issue_token --sub alice --roles employee
    python -m app.issue_token --sub ops --roles admin
"""

import argparse

from app.security import create_access_token

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sub", required=True)
    parser.add_argument("--roles", nargs="+", required=True)
    parser.add_argument("--ttl", type=int, default=None, help="minutes")
    args = parser.parse_args()
    
    print(create_access_token(args.sub, args.roles, args.ttl))


if __name__ == "__main__":
    main()