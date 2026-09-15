"""Tree-sitter based AST analysis.

Produces language-agnostic :class:`CodeEntity` records plus per-file structural
fingerprints. Everything here is deterministic; no model is involved.

Supported grammars: Python, JavaScript, TypeScript (+TSX), Java, C, C++.
Unsupported languages fall back to :func:`heuristic_file_summary`, which reports
only what can be counted without a parser and marks the file ``parsed=False``
rather than inventing structure.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterator

from .languages import supports_ast
from .limits import DEFAULT_LIMITS, AnalysisLimits

#: Node types that introduce a branch and therefore +1 cyclomatic complexity.
DECISION_NODES: frozenset[str] = frozenset(
    {
        "if_statement", "elif_clause", "else_if_clause",
        "for_statement", "for_in_statement", "for_in_clause", "enhanced_for_statement",
        "while_statement", "do_statement",
        "except_clause", "catch_clause", "catch_formal_parameter",
        "case_statement", "switch_case", "switch_label", "case_clause", "match_case",
        "conditional_expression", "ternary_expression",
        "boolean_operator",  # python `and`/`or`
        "assert_statement",
        "guard_statement",
    }
)

#: Node types that open a nesting level. Only *container* nodes are listed:
#: counting both ``if_statement`` and the ``block`` it owns would double-count
#: every level.
NESTING_NODES: frozenset[str] = frozenset(
    {"block", "statement_block", "compound_statement", "class_body", "switch_body"}
)

FUNCTION_NODES: frozenset[str] = frozenset(
    {
        "function_definition", "function_declaration",
        "method_definition", "method_declaration", "arrow_function",
        "function_expression", "generator_function_declaration",
        "constructor_declaration", "function_item",
    }
)

CLASS_NODES: frozenset[str] = frozenset(
    {
        "class_definition", "class_declaration", "class_specifier",
        "interface_declaration", "struct_specifier", "enum_declaration",
        "type_alias_declaration",
    }
)

IMPORT_NODES: frozenset[str] = frozenset(
    {
        "import_statement", "import_from_statement", "import_declaration",
        "preproc_include", "using_declaration",
    }
)

EXPORT_NODES: frozenset[str] = frozenset({"export_statement"})

COMMENT_NODES: frozenset[str] = frozenset({"comment", "line_comment", "block_comment"})

_SHORT_CIRCUIT = ("&&", "||", "and", "or")


@dataclass(slots=True)
class CodeEntity:
    """A function, method or class extracted from source."""

    file: str
    symbol: str
    kind: str  # "function" | "method" | "class"
    language: str
    start_line: int
    end_line: int
    complexity: int = 1
    max_nesting: int = 0
    param_count: int = 0
    has_doc: bool = False
    parent: str | None = None
    body_hash: str = ""
    structure_signature: str = ""
    source: str = ""

    @property
    def line_count(self) -> int:
        return max(1, self.end_line - self.start_line + 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "symbol": self.symbol,
            "type": self.kind,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "complexity": self.complexity,
            "max_nesting": self.max_nesting,
            "param_count": self.param_count,
            "line_count": self.line_count,
            "has_doc": self.has_doc,
            "parent": self.parent,
        }


@dataclass(slots=True)
class FileAST:
    """Per-file parse output."""

    path: str
    language: str
    parsed: bool = True
    entities: list[CodeEntity] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    max_nesting: int = 0
    has_errors: bool = False
    error_count: int = 0
    structural_fingerprint: str = ""
    node_histogram: dict[str, int] = field(default_factory=dict)
    parse_error: str | None = None

    @property
    def total_lines(self) -> int:
        return self.code_lines + self.comment_lines + self.blank_lines

    @property
    def functions(self) -> list[CodeEntity]:
        return [e for e in self.entities if e.kind in ("function", "method")]

    @property
    def classes(self) -> list[CodeEntity]:
        return [e for e in self.entities if e.kind == "class"]


@lru_cache(maxsize=16)
def _get_parser(language: str):
    """Load and cache a tree-sitter parser. Raises if the grammar is missing."""
    from tree_sitter_language_pack import get_parser

    return get_parser(language)  # type: ignore[arg-type]


def _node_text(node: Any, data: bytes) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _iter_nodes(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _entity_name(node: Any, data: bytes) -> str:
    """Best-effort symbol name across grammars."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, data)
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        inner = declarator.child_by_field_name("declarator")
        if inner is None:
            break
        declarator = inner
    if declarator is not None:
        return _node_text(declarator, data)
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "type_identifier", "field_identifier"):
            return _node_text(child, data)
    # Arrow functions and function expressions are usually bound to a variable.
    parent = node.parent
    if parent is not None and parent.type in ("variable_declarator", "assignment", "pair"):
        target = parent.child_by_field_name("name") or parent.child_by_field_name("left")
        if target is not None:
            return _node_text(target, data)
    return "<anonymous>"


def _export_name(node: Any, data: bytes) -> str:
    """Name of an exported symbol, falling back to the statement's first line."""
    declaration = node.child_by_field_name("declaration") or node.child_by_field_name("value")
    if declaration is None:
        for child in node.named_children:
            if child.type.endswith(("_declaration", "_statement", "declarator")):
                declaration = child
                break
    if declaration is not None:
        name = declaration.child_by_field_name("name")
        if name is not None:
            return _node_text(name, data)
        for child in declaration.named_children:
            if child.type == "variable_declarator":
                inner = child.child_by_field_name("name")
                if inner is not None:
                    return _node_text(inner, data)
    return _node_text(node, data).strip().split("\n")[0][:120]


def _count_params(node: Any) -> int:
    params = node.child_by_field_name("parameters")
    if params is None:
        for child in node.children:
            if child.type in ("formal_parameters", "parameters", "parameter_list"):
                params = child
                break
    if params is None:
        return 0
    skip = {",", "(", ")", "self", "this"}
    return sum(
        1
        for child in params.named_children
        if child.type not in ("comment",) and child.text.decode("utf-8", "replace") not in skip
    )


def _is_short_circuit(node: Any, data: bytes) -> bool:
    operator = node.child_by_field_name("operator")
    if operator is None:
        return False
    return _node_text(operator, data).strip() in _SHORT_CIRCUIT


def _complexity_and_nesting(node: Any, data: bytes) -> tuple[int, int]:
    """Cyclomatic complexity (McCabe, 1 + decision points) and max nesting depth
    inside ``node``."""
    complexity = 1
    max_depth = 0

    def visit(current: Any, depth: int) -> None:
        nonlocal complexity, max_depth
        node_type = current.type
        if node_type in DECISION_NODES:
            complexity += 1
        elif node_type == "binary_expression" and _is_short_circuit(current, data):
            complexity += 1
        next_depth = depth
        if node_type in NESTING_NODES:
            next_depth = depth + 1
            max_depth = max(max_depth, next_depth)
        for child in current.children:
            if child.type in FUNCTION_NODES and child is not current:
                # Nested functions are extracted as their own entity; their
                # complexity is not folded into the parent.
                continue
            visit(child, next_depth)

    visit(node, 0)
    # The entity's own body block is depth 1 and is not "nesting", so report
    # the number of levels *inside* the body.
    return complexity, max(0, max_depth - 1)


def _has_doc(node: Any, data: bytes, language: str) -> bool:
    if language == "python":
        body = node.child_by_field_name("body")
        if body is not None and body.named_child_count:
            first = body.named_children[0]
            # Grammar versions differ: the docstring is either a bare `string`
            # node or an `expression_statement` wrapping one.
            if first.type == "string":
                return True
            if first.type == "expression_statement" and first.named_child_count:
                return first.named_children[0].type == "string"
        return False
    previous = node.prev_sibling
    while previous is not None and previous.type in ("\n", ";"):
        previous = previous.prev_sibling
    if previous is not None and previous.type in COMMENT_NODES:
        text = _node_text(previous, data)
        return text.startswith("/**") or text.startswith("///") or len(text) > 40
    return False


def _structure_signature(node: Any, max_nodes: int = 400) -> str:
    """Hash of the node-type stream, ignoring identifiers and literals.

    Two functions with the same control-flow shape but different names produce
    the same signature, which is what structural similarity compares.
    """
    types: list[str] = []
    for current in _iter_nodes(node):
        if current.is_named and current.type not in COMMENT_NODES:
            types.append(current.type)
            if len(types) >= max_nodes:
                break
    return hashlib.sha256("|".join(types).encode()).hexdigest()[:32]


def _count_line_kinds(text: str, comment_line_numbers: set[int]) -> tuple[int, int, int]:
    code = comments = blank = 0
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            blank += 1
        elif index in comment_line_numbers:
            comments += 1
        else:
            code += 1
    return code, comments, blank


def parse_file(
    path: str,
    text: str,
    language: str,
    limits: AnalysisLimits = DEFAULT_LIMITS,
    keep_source: bool = False,
) -> FileAST:
    """Parse one source file.

    Never raises for malformed input: a file that fails to parse comes back with
    ``parsed=False`` and a ``parse_error``, so one bad file cannot fail a run.
    """
    if not supports_ast(language):
        return heuristic_file_summary(path, text, language)
    if len(text.encode("utf-8", "replace")) > limits.max_ast_file_bytes:
        result = heuristic_file_summary(path, text, language)
        result.parse_error = f"file exceeds AST budget of {limits.max_ast_file_bytes} bytes"
        return result

    try:
        parser = _get_parser(language)
        data = text.encode("utf-8", "replace")
        tree = parser.parse(data)
    except Exception as exc:  # pragma: no cover - grammar load failure
        result = heuristic_file_summary(path, text, language)
        result.parse_error = f"tree-sitter parse failed: {exc}"
        return result

    file_ast = FileAST(path=path, language=language)
    comment_lines: set[int] = set()
    histogram: dict[str, int] = {}
    error_count = 0
    file_nesting = 0

    for node in _iter_nodes(tree.root_node):
        node_type = node.type
        if node.is_named:
            histogram[node_type] = histogram.get(node_type, 0) + 1
        if node_type == "ERROR" or node.is_missing:
            error_count += 1
            continue
        if node_type in COMMENT_NODES:
            comment_lines.update(range(node.start_point[0] + 1, node.end_point[0] + 2))
            continue
        if node_type in IMPORT_NODES:
            file_ast.imports.append(_node_text(node, data).strip().replace("\n", " ")[:200])
            continue
        if node_type in EXPORT_NODES:
            file_ast.exports.append(_export_name(node, data))
        if node_type in FUNCTION_NODES or node_type in CLASS_NODES:
            is_class = node_type in CLASS_NODES
            complexity, nesting = _complexity_and_nesting(node, data)
            file_nesting = max(file_nesting, nesting)
            parent_name = None
            ancestor = node.parent
            while ancestor is not None:
                if ancestor.type in CLASS_NODES:
                    parent_name = _entity_name(ancestor, data)
                    break
                ancestor = ancestor.parent
            kind = "class" if is_class else ("method" if parent_name else "function")
            source = _node_text(node, data)
            file_ast.entities.append(
                CodeEntity(
                    file=path,
                    symbol=_entity_name(node, data),
                    kind=kind,
                    language=language,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    complexity=1 if is_class else complexity,
                    max_nesting=nesting,
                    param_count=0 if is_class else _count_params(node),
                    has_doc=_has_doc(node, data, language),
                    parent=parent_name,
                    body_hash=hashlib.sha256(source.encode()).hexdigest()[:32],
                    structure_signature=_structure_signature(node),
                    source=source if keep_source else "",
                )
            )

    code, comments, blank = _count_line_kinds(text, comment_lines)
    file_ast.code_lines = code
    file_ast.comment_lines = comments
    file_ast.blank_lines = blank
    file_ast.max_nesting = file_nesting
    file_ast.error_count = error_count
    file_ast.has_errors = error_count > 0
    file_ast.node_histogram = histogram
    file_ast.structural_fingerprint = _structure_signature(tree.root_node, max_nodes=2000)
    return file_ast


_LINE_COMMENT_RE = re.compile(r"^\s*(#|//|--|;|%)")


def heuristic_file_summary(path: str, text: str, language: str | None) -> FileAST:
    """Line accounting for languages without a bundled grammar.

    Reports only what can be counted reliably. ``parsed=False`` tells downstream
    analyzers not to treat missing entities as "this file has no functions".
    """
    code = comments = blank = 0
    for line in text.splitlines():
        if not line.strip():
            blank += 1
        elif _LINE_COMMENT_RE.match(line):
            comments += 1
        else:
            code += 1
    return FileAST(
        path=path,
        language=language or "unknown",
        parsed=False,
        code_lines=code,
        comment_lines=comments,
        blank_lines=blank,
        structural_fingerprint="",
    )
