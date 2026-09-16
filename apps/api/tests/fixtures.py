"""Synthetic repositories used to verify the analysis engine's judgements.

Each builder writes a real git repository to disk with a real commit history, so
the pipeline runs against it exactly as it would against a candidate's project.
The four shapes correspond to the scenarios in the product specification:

A. Excellent engineering       → high quality, high ownership, low risk
B. Large drop with no history  → verification required
C. Tutorial-derived scaffold   → tutorial similarity detected
D. Strong AI signals, strong   → effective AI augmentation
   engineering ownership
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/tmp",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def _git(repo: Path, *args: str, when: datetime | None = None) -> None:
    env = dict(GIT_ENV)
    if when is not None:
        stamp = when.isoformat()
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
        cwd=repo, env=env, check=True, capture_output=True, text=True,
    )


def _commit(repo: Path, message: str, when: datetime) -> None:
    _git(repo, "add", "-A", when=when)
    _git(repo, "commit", "-m", message, "--no-verify", when=when)


def _write(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _init(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "--quiet")
    return repo


_BASE_TIME = datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc)


def build_excellent_repository(root: Path) -> Path:
    """Repository A: iterative development, tests, docs, CI, clean code."""
    repo = _init(root, "excellent")
    day = _BASE_TIME

    _write(repo, "README.md", """# Ledger

A double-entry ledger service.

## Installation

```bash
pip install -e .
```

## Usage

```python
from ledger import Ledger
ledger = Ledger()
ledger.post("cash", "revenue", 100)
```

## Architecture

Three layers: `api/` holds HTTP routing, `services/` holds the posting rules,
and `models/` holds persistence. Entries are immutable; corrections are new
entries, which is why there is no update path.

## Design decisions

We chose integer minor units over Decimal because the ledger must round-trip
through JSON without precision loss. The trade-off is that currencies with
three decimal places need explicit scaling.

## Limitations

Multi-currency is not supported yet. Reporting is O(n) over entries.

## Contributing

Run `pytest` before opening a pull request.
""")
    _write(repo, "pyproject.toml", """[project]
name = "ledger"
version = "1.0.0"
dependencies = ["fastapi==0.115.0", "sqlalchemy==2.0.30", "psycopg==3.2.1"]

[project.optional-dependencies]
dev = ["pytest==8.3.0"]
""")
    _write(repo, "poetry.lock", "# generated lock file\n")
    _write(repo, "services/posting.py", '''"""Posting rules for the ledger."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """A single side of a double-entry posting."""

    account: str
    amount_minor: int


def validate_amount(amount_minor: int) -> None:
    """Reject amounts that cannot be posted."""
    if amount_minor == 0:
        raise ValueError("amount must be non-zero")
    if amount_minor < 0:
        raise ValueError("amount must be positive; use the opposite account")


def post(debit_account: str, credit_account: str, amount_minor: int) -> list[Entry]:
    """Create the balanced pair of entries for a posting."""
    validate_amount(amount_minor)
    if debit_account == credit_account:
        raise ValueError("debit and credit accounts must differ")
    return [
        Entry(account=debit_account, amount_minor=amount_minor),
        Entry(account=credit_account, amount_minor=-amount_minor),
    ]


def balance(entries: list[Entry], account: str) -> int:
    """Sum the entries for one account."""
    return sum(entry.amount_minor for entry in entries if entry.account == account)
''')
    _write(repo, "api/routes.py", '''"""HTTP routing for the ledger service."""

from services.posting import balance, post


def handle_post(payload: dict) -> dict:
    """Handle a posting request, returning the created entries."""
    try:
        entries = post(payload["debit"], payload["credit"], payload["amount_minor"])
    except (KeyError, ValueError) as exc:
        return {"error": str(exc), "status": 400}
    return {"entries": [entry.__dict__ for entry in entries], "status": 201}


def handle_balance(entries: list, account: str) -> dict:
    """Handle a balance query."""
    return {"account": account, "balance_minor": balance(entries, account)}
''')
    _commit(repo, "Add ledger posting rules and HTTP routes", day)

    day += timedelta(days=3)
    _write(repo, "tests/test_posting.py", '''"""Tests for the posting rules."""

import pytest

from services.posting import Entry, balance, post, validate_amount


def test_post_creates_balanced_entries():
    entries = post("cash", "revenue", 100)
    assert sum(entry.amount_minor for entry in entries) == 0


def test_post_rejects_same_account():
    with pytest.raises(ValueError):
        post("cash", "cash", 100)


def test_validate_amount_rejects_zero():
    with pytest.raises(ValueError):
        validate_amount(0)


def test_validate_amount_rejects_negative():
    with pytest.raises(ValueError):
        validate_amount(-5)


def test_balance_sums_one_account():
    entries = [Entry("cash", 100), Entry("cash", -30), Entry("revenue", -70)]
    assert balance(entries, "cash") == 70
''')
    _commit(repo, "Add tests covering the posting rules", day)

    day += timedelta(days=2)
    _write(repo, ".github/workflows/ci.yml", """name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .[dev]
      - run: pytest --cov=services
""")
    _commit(repo, "Run tests in CI on every push", day)

    day += timedelta(days=4)
    _write(repo, "services/posting.py", (repo / "services/posting.py").read_text().replace(
        '''def balance(entries: list[Entry], account: str) -> int:
    """Sum the entries for one account."""
    return sum(entry.amount_minor for entry in entries if entry.account == account)''',
        '''def balance(entries: list[Entry], account: str) -> int:
    """Sum the entries for one account."""
    return sum(entry.amount_minor for entry in entries if entry.account == account)


def trial_balance(entries: list[Entry]) -> dict[str, int]:
    """Balances for every account, which must sum to zero."""
    totals: dict[str, int] = {}
    for entry in entries:
        totals[entry.account] = totals.get(entry.account, 0) + entry.amount_minor
    return totals'''))
    _commit(repo, "Add trial balance report", day)

    day += timedelta(days=1)
    _write(repo, "tests/test_reporting.py", '''"""Tests for reporting."""

from services.posting import Entry, trial_balance


def test_trial_balance_sums_to_zero():
    entries = [Entry("cash", 100), Entry("revenue", -100)]
    assert sum(trial_balance(entries).values()) == 0
''')
    _commit(repo, "fix: trial balance ignored accounts with no entries", day)

    day += timedelta(days=5)
    _write(repo, "api/routes.py", (repo / "api/routes.py").read_text().replace(
        "def handle_balance(entries: list, account: str) -> dict:",
        "def handle_balance(entries: list, account: str) -> dict:  # noqa: D401"))
    _commit(repo, "refactor: extract error handling from the route layer", day)

    day += timedelta(days=2)
    _write(repo, "Dockerfile", """FROM python:3.11-slim
WORKDIR /srv
COPY . .
RUN pip install -e .
CMD ["python", "-m", "api"]
""")
    _commit(repo, "deploy: add container image for the ledger service", day)

    day += timedelta(days=3)
    _write(repo, "docs/architecture.md", """# Architecture

The ledger is append-only. A posting writes two entries in one transaction.
Reporting reads the entry table directly; there is no materialised balance,
because reconciliation bugs are harder to find than a slow query.
""")
    _commit(repo, "docs: describe the append-only architecture", day)
    _git(repo, "tag", "v1.0.0")
    return repo


def build_dropped_repository(root: Path) -> Path:
    """Repository B: a large, uniform codebase in one commit, no iteration."""
    repo = _init(root, "dropped")

    _write(repo, "README.md", "# Project\n\nA project.\n")
    for index in range(12):
        _write(repo, f"src/module_{index}.py", f'''"""Module {index}.

This module provides functionality for handling {index} operations.
"""


def process_data_{index}(data):
    """Process the data.

    Args:
        data: The data to process.

    Returns:
        The processed data.
    """
    result = []
    for item in data:
        if item is not None:
            result.append(item)
    return result


def validate_data_{index}(data):
    """Validate the data.

    Args:
        data: The data to validate.

    Returns:
        True if the data is valid.
    """
    if data is None:
        return False
    if len(data) == 0:
        return False
    return True


def transform_data_{index}(data):
    """Transform the data.

    Args:
        data: The data to transform.

    Returns:
        The transformed data.
    """
    # Here's how we transform each item
    output = []
    for item in data:
        output.append(item)
    return output
''')
    _commit(repo, "Initial commit", _BASE_TIME)
    return repo


def build_tutorial_repository(root: Path) -> Path:
    """Repository C: unmodified scaffolding and explicit tutorial attribution."""
    repo = _init(root, "tutorial")

    _write(repo, "README.md", """This is a [Next.js](https://nextjs.org) project bootstrapped with
[`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
```

Get started by editing `app/page.tsx`.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the Vercel Platform.

I built this while following this tutorial on YouTube.
""")
    _write(repo, "package.json", """{
  "name": "my-app",
  "dependencies": { "next": "^15.0.0", "react": "^19.0.0", "react-dom": "^19.0.0" }
}
""")
    _write(repo, "app/page.tsx", """export default function Home() {
  // Step 1: set up the page
  return (
    <main>
      <h1>Your Project Name</h1>
      {/* Step 2: add your content here */}
    </main>
  );
}
""")
    _write(repo, "app/lib/api.ts", """// Step 3: call the API
const API_KEY = "your-api-key-here";

export async function getData(id: string) {
  // Here's how we fetch the data
  const response = await fetch(`https://api.example.com/items/${id}`);
  return response.json();
}
""")
    _commit(repo, "initial commit from tutorial", _BASE_TIME)
    _write(repo, "app/page.tsx", (repo / "app/page.tsx").read_text() + "\n// done\n")
    _commit(repo, "update", _BASE_TIME + timedelta(hours=2))
    return repo


def build_augmented_repository(root: Path) -> Path:
    """Repository D: assistance signals present, engineering ownership strong.

    Uniform structured docstrings and repetitive scaffolding raise the
    AI-assistance estimate, while real iteration, tests, CI and documentation
    keep ownership high. The expected outcome is effective augmentation, not a
    penalty.
    """
    repo = _init(root, "augmented")
    day = _BASE_TIME

    _write(repo, "README.md", """# Inventory API

Stock tracking for a small warehouse.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
uvicorn app.main:app
```

## Architecture

`app/api` handles routing, `app/services` holds stock rules and `app/models`
holds persistence. Stock movements are events; the on-hand quantity is derived.

## Design decisions

I used events rather than a mutable quantity column because two concurrent
picks were producing lost updates. The trade-off is that reads need an
aggregate, which is why `on_hand` is cached per SKU.

## Limitations

No multi-warehouse support. The cache is invalidated on write, not on a TTL.
""")
    _write(repo, "requirements.txt", "fastapi==0.115.0\nuvicorn==0.30.0\npytest==8.3.0\n")
    for name in ("items", "stock", "suppliers"):
        _write(repo, f"app/services/{name}.py", f'''"""Service layer for {name}."""

from typing import Any


def list_{name}(session: Any) -> list[dict]:
    """Return all {name}.

    Args:
        session: The database session.

    Returns:
        A list of {name} records.
    """
    return session.query("{name}").all()


def get_{name}(session: Any, identifier: str) -> dict | None:
    """Return one record by identifier.

    Args:
        session: The database session.
        identifier: The record identifier.

    Returns:
        The record, or None when it does not exist.
    """
    return session.query("{name}").get(identifier)


def create_{name}(session: Any, payload: dict) -> dict:
    """Create a record.

    Args:
        session: The database session.
        payload: The record payload.

    Returns:
        The created record.
    """
    record = session.create("{name}", payload)
    session.commit()
    return record
''')
    _write(repo, "app/api/routes.py", '''"""HTTP routes for the inventory API."""

from typing import Any

# Here's how we wire each resource to its service.
# Example usage:
#     router = build_router(session)


def build_router(session: Any) -> dict:
    """Build the routing table.

    Args:
        session: The database session.

    Returns:
        A mapping of path to handler.
    """
    # Step 1: register the item routes
    routes = {}
    routes["/items"] = lambda: list_items_handler(session)
    # Step 2: register the stock routes
    routes["/stock"] = lambda: list_stock_handler(session)
    # Step 3: register the supplier routes
    routes["/suppliers"] = lambda: list_suppliers_handler(session)
    return routes


def list_items_handler(session: Any) -> list:
    """Handle the items listing.

    Args:
        session: The database session.

    Returns:
        The items.
    """
    return session.query("items").all()


def list_stock_handler(session: Any) -> list:
    """Handle the stock listing.

    Args:
        session: The database session.

    Returns:
        The stock records.
    """
    return session.query("stock").all()


def list_suppliers_handler(session: Any) -> list:
    """Handle the suppliers listing.

    Args:
        session: The database session.

    Returns:
        The suppliers.
    """
    return session.query("suppliers").all()
''')
    _commit(repo, "Add service layer for items, stock and suppliers", day)

    day += timedelta(days=2)
    _write(repo, "app/services/stock.py", (repo / "app/services/stock.py").read_text() + '''

def on_hand(session: Any, sku: str) -> int:
    """Derive the on-hand quantity from stock movements.

    Movements are the source of truth because a mutable quantity column lost
    updates under concurrent picks.
    """
    movements = session.query("movements").filter(sku=sku).all()
    total = 0
    for movement in movements:
        if movement["kind"] == "receipt":
            total += movement["quantity"]
        elif movement["kind"] == "pick":
            total -= movement["quantity"]
        else:
            raise ValueError(f"unknown movement kind: {movement['kind']}")
    return total
''')
    _commit(repo, "fix: on-hand quantity lost updates under concurrent picks", day)

    day += timedelta(days=3)
    _write(repo, "tests/test_stock.py", '''"""Tests for stock derivation."""

import pytest

from app.services.stock import on_hand


class FakeSession:
    def __init__(self, movements):
        self._movements = movements

    def query(self, _table):
        return self

    def filter(self, **_kwargs):
        return self

    def all(self):
        return self._movements


def test_on_hand_sums_receipts_and_picks():
    session = FakeSession([
        {"kind": "receipt", "quantity": 10},
        {"kind": "pick", "quantity": 3},
    ])
    assert on_hand(session, "SKU-1") == 7


def test_on_hand_rejects_unknown_movement():
    session = FakeSession([{"kind": "teleport", "quantity": 1}])
    with pytest.raises(ValueError):
        on_hand(session, "SKU-1")
''')
    _commit(repo, "test: cover stock derivation including the failure path", day)

    day += timedelta(days=2)
    _write(repo, ".github/workflows/ci.yml", """name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest
""")
    _commit(repo, "ci: run pytest on every push", day)

    day += timedelta(days=4)
    _write(repo, "app/services/cache.py", '''"""Per-SKU cache for derived quantities."""


class StockCache:
    """Write-through cache invalidated on movement, not on a timer."""

    def __init__(self) -> None:
        self._values: dict[str, int] = {}

    def get(self, sku: str) -> int | None:
        return self._values.get(sku)

    def set(self, sku: str, quantity: int) -> None:
        self._values[sku] = quantity

    def invalidate(self, sku: str) -> None:
        self._values.pop(sku, None)
''')
    _commit(repo, "perf: cache derived on-hand quantities per SKU", day)

    day += timedelta(days=2)
    _write(repo, "docs/decisions.md", """# Decisions

## Events over a quantity column

Two pickers hitting the same SKU produced lost updates. Movements are now the
source of truth and the quantity is derived, with a per-SKU cache invalidated on
write.
""")
    _commit(repo, "docs: record the events-over-quantity decision", day)
    return repo


BUILDERS = {
    "excellent": build_excellent_repository,
    "dropped": build_dropped_repository,
    "tutorial": build_tutorial_repository,
    "augmented": build_augmented_repository,
}


def local_fetcher(path: Path):
    """A :class:`SourceFetcher` that serves an already-present working tree.

    Used by the integration tests so they exercise the real pipeline without a
    network round trip, and without relaxing the production fetcher's rule that
    only https remotes may be cloned.
    """
    from repolens_github import FetchedRepository

    def fetch(repository, token, limits):  # noqa: ANN001 - matches SourceFetcher
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True,
            env=GIT_ENV, check=False,
        ).stdout.strip()
        return FetchedRepository(
            path=path, clone_url=f"file://{path}", default_branch="main",
            head_sha=head or None,
            size_bytes=sum(f.stat().st_size for f in path.rglob("*") if f.is_file()),
            shallow=False, _temp_root=None,
        )

    return fetch
