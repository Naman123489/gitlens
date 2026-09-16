#!/usr/bin/env python
"""Create or promote an administrator.

    python scripts/create_admin.py --email you@example.com --name "Your Name"

Administrators are provisioned here rather than through the sign-up form, so
privilege escalation is never one HTTP request away. The password is read from
stdin without echo, or generated when --generate-password is passed.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import func  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models import User  # noqa: E402
from app.services import audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote a RepoLens administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--generate-password", action="store_true")
    args = parser.parse_args()

    email = args.email.strip().lower()

    if args.generate_password:
        password = secrets.token_urlsafe(18)
    else:
        password = getpass.getpass("Password (min 10 characters): ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(f"Password rejected: {exc}", file=sys.stderr)
        return 1

    with session_scope() as db:
        user = db.query(User).filter(func.lower(User.email) == email).one_or_none()
        if user is None:
            user = User(email=email, full_name=args.name or email, role="ADMIN",
                        password_hash=password_hash)
            db.add(user)
            action = "created"
        else:
            user.role = "ADMIN"
            user.password_hash = password_hash
            user.is_active = True
            db.add(user)
            action = "promoted"
        db.flush()
        audit.record(db, "admin.provisioned", actor=user, target_type="user", target_id=user.id,
                     detail={"action": action, "via": "scripts/create_admin.py"})

    print(f"Administrator {action}: {email}")
    if args.generate_password:
        print(f"Generated password: {password}")
        print("Store it now — it is not recoverable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
