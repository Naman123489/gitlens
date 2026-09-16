#!/usr/bin/env python
"""Seed development demo data.

    python scripts/seed_demo.py            # create or update demo records
    python scripts/seed_demo.py --reset    # remove demo records first
    python scripts/seed_demo.py --purge    # remove demo records and stop

Refuses to run against a production environment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.seed.demo import DEMO_PASSWORD, seed_demo_data, purge_demo_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed RepoLens demo data.")
    parser.add_argument("--reset", action="store_true", help="remove demo records first")
    parser.add_argument("--purge", action="store_true", help="remove demo records and exit")
    parser.add_argument("--force", action="store_true", help="allow running outside development")
    args = parser.parse_args()

    settings = get_settings()
    if settings.is_production and not args.force:
        print(
            f"Refusing to seed demo data in '{settings.environment}'. "
            "Demo records must never mix with production users. Use --force only if you are "
            "certain this database is disposable.",
            file=sys.stderr,
        )
        return 1

    with session_scope() as db:
        if args.purge:
            print(f"Removed {purge_demo_data(db)} demo record(s).")
            return 0
        counts = seed_demo_data(db, reset=args.reset)

    print("Demo data seeded:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    print()
    print("Sign in with any of these demo accounts:")
    print(f"  interviewer  priya.raman@repolens.invalid   {DEMO_PASSWORD}")
    print(f"  student      alex.mehta@repolens.invalid    {DEMO_PASSWORD}")
    print(f"  student      riya.sharma@repolens.invalid   {DEMO_PASSWORD}")
    print(f"  student      dev.patel@repolens.invalid     {DEMO_PASSWORD}")
    print()
    print("No scores are seeded. Open a repository and run an analysis — every score in "
          "RepoLens comes from real analysis of real code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
