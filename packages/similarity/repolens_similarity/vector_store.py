"""Vector storage abstraction.

Two backends share one interface:

* :class:`PgVectorStore` uses the PostgreSQL ``vector`` type and an ANN index.
  This is the backend used by ``docker-compose.yml`` (image
  ``pgvector/pgvector:pg16``).
* :class:`ArrayVectorStore` stores embeddings as ``double precision[]`` and
  computes cosine similarity in Python. It exists because the ``vector``
  extension is not available in every PostgreSQL installation; it is correct but
  scans linearly, so it is only appropriate for prototype-scale corpora.

:func:`detect_backend` picks the right one at runtime by asking the database
whether the extension is installed, rather than assuming.
"""

from __future__ import annotations

from typing import Any, Protocol

from repolens_shared.textutils import dense_cosine


class VectorStore(Protocol):
    backend: str

    def upsert(self, chunk_id: str, vector: list[float], metadata: dict[str, Any]) -> None: ...

    def search(self, vector: list[float], limit: int,
               exclude_repository_id: str | None = None) -> list[tuple[str, float, dict[str, Any]]]: ...


class InMemoryVectorStore:
    """Used by tests and by the analyzer when it compares within a single run."""

    backend = "memory"

    def __init__(self) -> None:
        self._items: dict[str, tuple[list[float], dict[str, Any]]] = {}

    def upsert(self, chunk_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._items[chunk_id] = (vector, metadata)

    def search(
        self, vector: list[float], limit: int, exclude_repository_id: str | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]:
        scored: list[tuple[str, float, dict[str, Any]]] = []
        for chunk_id, (candidate, metadata) in self._items.items():
            if exclude_repository_id and metadata.get("repository_id") == exclude_repository_id:
                continue
            scored.append((chunk_id, dense_cosine(vector, candidate), metadata))
        scored.sort(key=lambda item: -item[1])
        return scored[:limit]

    def __len__(self) -> int:
        return len(self._items)


def pgvector_available(connection) -> bool:
    """True when the ``vector`` extension is installed in the connected database."""
    row = connection.exec_driver_sql(
        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
    ).first()
    return row is not None
