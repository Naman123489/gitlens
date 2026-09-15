"""AST structural similarity.

Compares the *shape* of code rather than its text: two functions with the same
control-flow skeleton match even if every identifier, literal and comment
differs. Implemented as a bag-of-subtree-shapes comparison over tree-sitter
node types, which is language-agnostic for the supported grammars.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from repolens_analysis.ast_engine import CodeEntity, FileAST
from repolens_shared.textutils import cosine_similarity


@dataclass(frozen=True, slots=True)
class StructuralMatch:
    left: str
    right: str
    similarity: float
    kind: str  # "identical_shape" | "similar_shape"


def shape_vector(histogram: dict[str, int]) -> dict[str, float]:
    """Sub-linear (log) weighted node-type vector.

    Log weighting stops a file with 400 ``identifier`` nodes from drowning out
    the control-flow nodes that carry the structural signal.
    """
    import math

    return {key: 1.0 + math.log(count) for key, count in histogram.items() if count > 0}


def file_shape_similarity(left: FileAST, right: FileAST) -> float:
    if not left.node_histogram or not right.node_histogram:
        return 0.0
    return cosine_similarity(shape_vector(left.node_histogram), shape_vector(right.node_histogram))


def entity_signature_index(entities: list[CodeEntity]) -> dict[str, list[CodeEntity]]:
    index: dict[str, list[CodeEntity]] = {}
    for entity in entities:
        if entity.kind == "class" or not entity.structure_signature:
            continue
        index.setdefault(entity.structure_signature, []).append(entity)
    return index


def identical_shape_groups(entities: list[CodeEntity], min_lines: int = 6) -> list[list[CodeEntity]]:
    """Groups of functions that share an exact structural signature.

    Trivial functions are excluded via ``min_lines`` — every one-line getter in
    a codebase has the same shape, and that is not interesting.
    """
    groups: list[list[CodeEntity]] = []
    for group in entity_signature_index(entities).values():
        substantial = [e for e in group if e.line_count >= min_lines]
        if len(substantial) > 1:
            groups.append(substantial)
    return sorted(groups, key=lambda g: -len(g))


def compare_entities(left: CodeEntity, right: CodeEntity) -> float:
    """Structural similarity of two entities in [0, 1]."""
    if left.structure_signature and left.structure_signature == right.structure_signature:
        return 1.0
    left_profile = Counter(
        {
            "complexity": left.complexity, "nesting": left.max_nesting,
            "params": left.param_count, "lines": left.line_count,
        }
    )
    right_profile = Counter(
        {
            "complexity": right.complexity, "nesting": right.max_nesting,
            "params": right.param_count, "lines": right.line_count,
        }
    )
    return cosine_similarity(
        {k: float(v) for k, v in left_profile.items()},
        {k: float(v) for k, v in right_profile.items()},
    )
