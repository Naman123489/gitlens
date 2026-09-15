"""Per-file style profiling.

Used by the AI-usage analyzer to look for *discontinuity*: a codebase written by
one person over time tends to be stylistically consistent, so sharp shifts
between files are a signal worth investigating — from any cause, including a
second contributor, a copied module or generated code.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .ast_engine import FileAST

_INDENT_RE = re.compile(r"^([ \t]+)")
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_RE = re.compile(r"^[a-z]+(?:[A-Z][a-z0-9]*)+$")


@dataclass(slots=True)
class StyleProfile:
    path: str
    indent_width: int
    uses_tabs: bool
    avg_line_length: float
    max_line_length: int
    comment_ratio: float
    docstring_ratio: float
    snake_ratio: float
    camel_ratio: float
    quote_preference: str
    trailing_comma_ratio: float
    avg_function_length: float
    type_annotation_ratio: float

    def vector(self) -> dict[str, float]:
        return {
            "indent_width": float(self.indent_width),
            "uses_tabs": 1.0 if self.uses_tabs else 0.0,
            "avg_line_length": self.avg_line_length,
            "comment_ratio": self.comment_ratio * 100,
            "docstring_ratio": self.docstring_ratio * 100,
            "snake_ratio": self.snake_ratio * 100,
            "camel_ratio": self.camel_ratio * 100,
            "avg_function_length": self.avg_function_length,
            "type_annotation_ratio": self.type_annotation_ratio * 100,
        }


def profile_file(file_ast: FileAST, text: str) -> StyleProfile:
    lines = text.splitlines()
    indents: list[int] = []
    tabs = False
    for line in lines:
        match = _INDENT_RE.match(line)
        if match:
            whitespace = match.group(1)
            if "\t" in whitespace:
                tabs = True
            else:
                indents.append(len(whitespace))
    widths = [i for i in indents if i > 0]
    indent_width = statistics.mode(widths) if widths else 4

    lengths = [len(l) for l in lines if l.strip()] or [0]
    functions = file_ast.functions
    names = [e.symbol for e in file_ast.entities if e.symbol != "<anonymous>"]
    snake = sum(1 for n in names if _SNAKE_RE.match(n))
    camel = sum(1 for n in names if _CAMEL_RE.match(n))

    single = text.count("'")
    double = text.count('"')
    annotated = len(re.findall(r"(?:\)\s*->|:\s*(?:str|int|float|bool|list|dict|[A-Z]\w+)\s*[,)=\n])", text))

    return StyleProfile(
        path=file_ast.path,
        indent_width=indent_width,
        uses_tabs=tabs,
        avg_line_length=sum(lengths) / len(lengths),
        max_line_length=max(lengths),
        comment_ratio=file_ast.comment_lines / max(1, file_ast.total_lines),
        docstring_ratio=(sum(1 for f in functions if f.has_doc) / len(functions)) if functions else 0.0,
        snake_ratio=snake / max(1, len(names)),
        camel_ratio=camel / max(1, len(names)),
        quote_preference="single" if single > double * 1.5 else ("double" if double > single * 1.5 else "mixed"),
        trailing_comma_ratio=text.count(",\n") / max(1, len(lines)),
        avg_function_length=(sum(f.line_count for f in functions) / len(functions)) if functions else 0.0,
        type_annotation_ratio=min(1.0, annotated / max(1, len(functions))) if functions else 0.0,
    )


def style_discontinuity(profiles: list[StyleProfile]) -> tuple[float, list[tuple[str, float]]]:
    """Return ``(discontinuity 0..1, per-file deviation)``.

    Deviation is the normalised distance of a file's style vector from the
    repository median. A repository written consistently scores near 0.
    """
    if len(profiles) < 3:
        return 0.0, []

    vectors = [p.vector() for p in profiles]
    keys = sorted(vectors[0])
    medians = {k: statistics.median([v[k] for v in vectors]) for k in keys}
    spreads = {
        k: (statistics.pstdev([v[k] for v in vectors]) or 1.0) for k in keys
    }

    deviations: list[tuple[str, float]] = []
    for profile, vector in zip(profiles, vectors):
        distance = sum(abs(vector[k] - medians[k]) / spreads[k] for k in keys) / len(keys)
        deviations.append((profile.path, round(distance, 3)))

    values = [d for _, d in deviations]
    # A repository is "discontinuous" when a meaningful minority of files sit
    # far from the median, not when one outlier exists.
    outliers = [v for v in values if v > 1.5]
    discontinuity = min(1.0, (len(outliers) / len(values)) * 2.0)
    deviations.sort(key=lambda item: -item[1])
    return round(discontinuity, 4), deviations[:10]
