"""Winnowing fingerprints (Schleimer, Wilkerson & Aiken, SIGMOD 2003).

k-grams of the normalised token stream are hashed, then a minimum hash is
selected from each sliding window. This guarantees that any shared substring of
at least ``window + k - 1`` tokens produces at least one shared fingerprint,
while keeping the stored fingerprint set small.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .normalize import token_stream

K_GRAM = 12
WINDOW = 8


@dataclass(frozen=True, slots=True)
class Fingerprint:
    value: int
    position: int


def _hash_gram(tokens: tuple[str, ...]) -> int:
    digest = hashlib.blake2b("\x00".join(tokens).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def fingerprints(source: str, k: int = K_GRAM, window: int = WINDOW) -> list[Fingerprint]:
    """Winnowed fingerprints for a source string."""
    tokens = token_stream(source)
    if len(tokens) < k:
        return []
    hashes = [
        _hash_gram(tuple(tokens[i : i + k])) for i in range(len(tokens) - k + 1)
    ]
    selected: dict[int, int] = {}
    previous_index = -1
    for start in range(max(1, len(hashes) - window + 1)):
        chunk = hashes[start : start + window]
        if not chunk:
            break
        minimum = min(chunk)
        # Rightmost occurrence of the minimum, per the winnowing paper.
        offset = len(chunk) - 1 - chunk[::-1].index(minimum)
        index = start + offset
        if index != previous_index:
            selected.setdefault(minimum, index)
            previous_index = index
    return [Fingerprint(value=value, position=position) for value, position in selected.items()]


def fingerprint_set(source: str, k: int = K_GRAM, window: int = WINDOW) -> set[int]:
    return {f.value for f in fingerprints(source, k, window)}


def jaccard(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def containment(a: set[int], b: set[int]) -> float:
    """Fraction of ``a`` also present in ``b``.

    More useful than Jaccard when comparing a small file against a large corpus:
    a 40-line function copied into a 4000-line file has low Jaccard but high
    containment.
    """
    if not a:
        return 0.0
    return len(a & b) / len(a)
