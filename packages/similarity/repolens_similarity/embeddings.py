"""Code embeddings.

RepoLens treats embedding generation as a pluggable service:

* :class:`HashingEmbedder` is the built-in, dependency-free default. It is a
  feature-hashing vectoriser over normalised code tokens and token bigrams —
  a real, deterministic, reproducible embedding, but a **lexical** one. It
  captures "these two chunks use the same constructs in the same proportions",
  not "these two chunks mean the same thing".
* :class:`EmbeddingProvider` is the protocol a neural provider implements. The
  API server injects one when ``LLM_API_KEY``/embedding configuration is present.

The distinction matters and is surfaced to users: results computed with the
hashing embedder are labelled ``lexical`` so nobody mistakes them for semantic
matches.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from .normalize import token_stream

DEFAULT_DIMENSIONS = 256


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Anything that can turn code into vectors."""

    name: str
    dimensions: int
    kind: str  # "lexical" | "neural"

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    """Deterministic feature-hashing embedder over normalised code tokens."""

    name = "hashing-v1"
    kind = "lexical"

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _index(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        # The sign bit removes the systematic bias that plain hashing introduces.
        return value % self.dimensions, 1.0 if (value >> 63) & 1 else -1.0

    def embed_one(self, text: str) -> list[float]:
        tokens = token_stream(text, keep_identifiers=True)
        if not tokens:
            return [0.0] * self.dimensions
        vector = [0.0] * self.dimensions
        features: list[str] = list(tokens)
        features.extend(f"{a}\x00{b}" for a, b in zip(tokens, tokens[1:]))
        counts: dict[str, int] = {}
        for feature in features:
            counts[feature] = counts.get(feature, 0) + 1
        for feature, count in counts.items():
            index, sign = self._index(feature)
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


def get_default_embedder() -> HashingEmbedder:
    return HashingEmbedder()
