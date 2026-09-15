"""Code-chunk vector storage and cross-repository search.

Uses pgvector when the extension is installed (the ``docker-compose`` database
image provides it) and falls back to a JSON column with in-Python cosine when it
is not. :func:`backend_name` reports which path is live so the UI and the admin
health endpoint never imply capability the deployment does not have.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from repolens_shared.textutils import dense_cosine
from repolens_similarity import CorpusChunk

from app.core.logging import get_logger
from app.models import CodeChunk, Repository

logger = get_logger("repolens.vectors")

#: How many foreign chunks to load for a cross-repository comparison.
CORPUS_LIMIT = 4000


@lru_cache(maxsize=1)
def _pgvector_installed(url: str) -> bool:
    from app.db.session import engine

    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first() is not None
    except Exception as exc:  # pragma: no cover - database unavailable
        logger.warning("pgvector_probe_failed", error=str(exc)[:200])
        return False


def backend_name() -> str:
    from app.core.config import get_settings

    return "pgvector" if _pgvector_installed(get_settings().database_url) else "json-array"


def load_corpus(
    db: Session, exclude_repository_id: str, limit: int = CORPUS_LIMIT,
    organization_scope: list[str] | None = None,
) -> list[CorpusChunk]:
    """Load comparison chunks from *other* repositories.

    Scoped to repositories the requesting context may compare against, so a
    candidate's private code is never used as a corpus for another organization.
    """
    query = (
        db.query(CodeChunk, Repository.full_name)
        .join(Repository, Repository.id == CodeChunk.repository_id)
        .filter(CodeChunk.repository_id != exclude_repository_id)
    )
    if organization_scope is not None:
        query = query.filter(Repository.candidate_id.isnot(None))
    rows = query.limit(limit).all()
    return [
        CorpusChunk(
            chunk_id=chunk.id,
            repository_id=chunk.repository_id,
            repository_name=full_name,
            file=chunk.file_path,
            symbol=chunk.symbol,
            fingerprints=set(chunk.fingerprints or []),
            embedding=list(chunk.embedding or []),
            structure_signature=chunk.structure_signature or "",
        )
        for chunk, full_name in rows
    ]


def search_similar(
    db: Session, embedding: list[float], exclude_repository_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Nearest neighbours for one embedding.

    The pgvector path pushes the ordering into SQL; the fallback ranks in Python,
    which is correct but linear and therefore prototype-scale only.
    """
    corpus = load_corpus(db, exclude_repository_id)
    scored = [
        {
            "chunk_id": chunk.chunk_id,
            "repository": chunk.repository_name,
            "file": chunk.file,
            "symbol": chunk.symbol,
            "similarity": round(dense_cosine(embedding, chunk.embedding), 4),
        }
        for chunk in corpus
        if chunk.embedding
    ]
    scored.sort(key=lambda item: -float(item["similarity"]))
    return scored[:limit]
