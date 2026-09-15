"""Language detection.

Extension-based with shebang and content fallbacks. Deliberately conservative:
an unknown language yields ``None`` rather than a guess, and downstream
analyzers degrade gracefully instead of inventing metrics.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

#: Extension -> canonical language name.
EXTENSION_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript", ".cts": "typescript",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php", ".cs": "c_sharp",
    ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".sql": "sql", ".r": "r", ".m": "objc", ".dart": "dart", ".lua": "lua",
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss", ".sass": "scss",
    ".vue": "vue", ".svelte": "svelte",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".xml": "xml",
    ".md": "markdown", ".mdx": "markdown", ".rst": "rst", ".txt": "text",
    ".ipynb": "jupyter",
    ".tf": "terraform", ".proto": "protobuf", ".graphql": "graphql", ".gql": "graphql",
}

#: Languages for which we have a tree-sitter grammar and a real AST extractor.
AST_SUPPORTED: frozenset[str] = frozenset(
    {"python", "javascript", "typescript", "tsx", "java", "c", "cpp"}
)

#: Languages counted as "source code" for quality/ownership purposes.
PROGRAMMING_LANGUAGES: frozenset[str] = frozenset(
    {
        "python", "javascript", "typescript", "tsx", "java", "c", "cpp", "go", "rust",
        "ruby", "php", "c_sharp", "kotlin", "swift", "scala", "bash", "dart", "lua",
        "objc", "r", "sql", "vue", "svelte",
    }
)

MARKUP_LANGUAGES: frozenset[str] = frozenset({"html", "css", "scss", "xml"})
DATA_LANGUAGES: frozenset[str] = frozenset({"json", "yaml", "toml", "xml"})
DOC_LANGUAGES: frozenset[str] = frozenset({"markdown", "rst", "text"})

_FILENAME_MAP: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "make",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "procfile": "text",
}

_SHEBANG_RE = re.compile(r"^#!.*?\b(python[\d.]*|node|bash|sh|ruby|perl|php)\b")
_SHEBANG_LANGS = {"python": "python", "node": "javascript", "bash": "bash", "sh": "bash",
                  "ruby": "ruby", "perl": "perl", "php": "php"}


def detect_language(path: str, first_line: str | None = None) -> str | None:
    """Return the canonical language for ``path`` or ``None`` if unknown."""
    name = PurePosixPath(path).name.lower()
    if name in _FILENAME_MAP:
        return _FILENAME_MAP[name]
    if name.startswith("dockerfile"):
        return "dockerfile"
    suffix = PurePosixPath(name).suffix
    if suffix in EXTENSION_MAP:
        return EXTENSION_MAP[suffix]
    if first_line:
        match = _SHEBANG_RE.match(first_line.strip())
        if match:
            token = match.group(1)
            base = re.sub(r"[\d.]+$", "", token)
            return _SHEBANG_LANGS.get(base)
    return None


def is_programming_language(language: str | None) -> bool:
    return language in PROGRAMMING_LANGUAGES


def supports_ast(language: str | None) -> bool:
    return language in AST_SUPPORTED
