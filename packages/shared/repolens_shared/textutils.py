"""Small deterministic text helpers used across analyzers."""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def shannon_entropy(value: str) -> float:
    """Entropy in bits per character. Used by the secret detector to separate
    real credentials from placeholder strings."""
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def split_identifier(identifier: str) -> list[str]:
    """Split ``parse_jobDescriptionV2`` into ``['parse','job','description','v2']``."""
    parts: list[str] = []
    for chunk in re.split(r"[_\-\s]+", identifier):
        if not chunk:
            continue
        parts.extend(p.lower() for p in _CAMEL_RE.split(chunk) if p)
    return parts


def tokenize_words(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two sparse vectors."""
    if not a or not b:
        return 0.0
    common = a.keys() & b.keys()
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def dense_cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scale(value: float, worst: float, best: float) -> float:
    """Linearly map ``value`` onto 0..100 between ``worst`` and ``best``.

    Supports inverted ranges (``worst`` > ``best``) for metrics where lower is
    better, such as average cyclomatic complexity.
    """
    if worst == best:
        return 100.0
    ratio = (value - worst) / (best - worst)
    return clamp(ratio * 100.0)


def truncate(text: str, limit: int = 240) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
