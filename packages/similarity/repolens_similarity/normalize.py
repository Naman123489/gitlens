"""Source normalisation for similarity comparison.

Similarity must survive reformatting and renaming, so the normaliser strips
comments and whitespace and rewrites identifiers and literals to placeholders.
Language keywords are preserved, which is what keeps the comparison meaningful.
"""

from __future__ import annotations

import re

#: Keywords kept verbatim during identifier normalisation. A union across the
#: supported languages: over-keeping is safe, it only makes matching stricter.
KEYWORDS: frozenset[str] = frozenset(
    """
    if elif else for while do switch case default break continue return yield
    try except catch finally raise throw with as import from export require
    def function class struct interface enum extends implements new delete
    public private protected static final const let var abstract override
    async await lambda pass and or not in is None True False null nil true false
    undefined this self super typeof instanceof void sizeof union namespace
    template using typedef virtual inline package throws synchronized
    """.split()
)

_COMMENT_PATTERNS = (
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r"//[^\n]*"),
    re.compile(r"#[^\n]*"),
    re.compile(r'"""(?:.|\n)*?"""'),
    re.compile(r"'''(?:.|\n)*?'''"),
)
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`')
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_comments(source: str) -> str:
    for pattern in _COMMENT_PATTERNS:
        source = pattern.sub(" ", source)
    return source


def normalize_source(source: str, keep_identifiers: bool = False) -> str:
    """Return a canonical form of ``source``.

    With ``keep_identifiers=False`` (the default) every non-keyword identifier
    becomes ``V`` and every literal becomes ``L``, so ``total = price * 2`` and
    ``sum = cost * 5`` normalise to the same token stream.
    """
    text = strip_comments(source)
    text = _STRING_RE.sub(" L ", text)
    text = _NUMBER_RE.sub(" L ", text)
    if not keep_identifiers:
        text = _IDENTIFIER_RE.sub(
            lambda m: m.group(0) if m.group(0) in KEYWORDS else "V", text
        )
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def token_stream(source: str, keep_identifiers: bool = False) -> list[str]:
    normalized = normalize_source(source, keep_identifiers=keep_identifiers)
    return [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[^\sA-Za-z0-9_]", normalized) if t]
