"""RepoLens code similarity engine."""

from .analyzer import (
    ANALYZER_NAME,
    ANALYZER_VERSION,
    ChunkRecord,
    CorpusChunk,
    SimilarityInput,
    analyze_similarity,
    build_chunks,
)
from .embeddings import DEFAULT_DIMENSIONS, EmbeddingProvider, HashingEmbedder, get_default_embedder
from .fingerprint import containment, fingerprint_set, fingerprints, jaccard
from .normalize import normalize_source, token_stream
from .structural import file_shape_similarity, identical_shape_groups
from .tutorial import TUTORIAL_SIGNALS, TutorialAssessment, assess_tutorial_signals
from .vector_store import InMemoryVectorStore, VectorStore, pgvector_available

__all__ = [
    "ANALYZER_NAME", "ANALYZER_VERSION", "ChunkRecord", "CorpusChunk", "DEFAULT_DIMENSIONS",
    "EmbeddingProvider", "HashingEmbedder", "InMemoryVectorStore", "SimilarityInput",
    "TUTORIAL_SIGNALS", "TutorialAssessment", "VectorStore", "analyze_similarity",
    "assess_tutorial_signals", "build_chunks", "containment", "file_shape_similarity",
    "fingerprint_set", "fingerprints", "get_default_embedder", "identical_shape_groups",
    "jaccard", "normalize_source", "pgvector_available", "token_stream",
]
