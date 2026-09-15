"""RepoLens repository analysis engine.

Pure-Python, importable without a database or web server so that every analyzer
is unit-testable against synthetic repositories.
"""

from .architecture import ArchitectureInput, analyze_architecture, build_import_graph
from .ast_engine import CodeEntity, FileAST, heuristic_file_summary, parse_file
from .ai_usage import AIUsageInput, analyze_ai_usage, classify as classify_ai_usage
from .classification import classify, is_dependency_manifest, is_test_path, should_ignore
from .dependencies import Dependency, DependencyInput, analyze_dependencies, parse_dependencies
from .documentation import DocumentationInput, analyze_documentation, find_readme
from .git_collect import Commit, GitHistory, collect_history
from .git_history import HistorySignals, analyze_git_history, classify_intent
from .languages import detect_language, is_programming_language, supports_ast
from .limits import DEFAULT_LIMITS, AnalysisLimits, LimitExceeded
from .metrics import MetricsInput, analyze_metrics, duplication_ratio
from .ownership import OwnershipInput, analyze_ai_utilization, analyze_ownership
from .style import StyleProfile, profile_file, style_discontinuity
from .testing import TestingInput, analyze_testing
from .walker import RepoFile, WalkResult, hash_bytes, walk_repository

__all__ = [
    "AIUsageInput", "AnalysisLimits", "ArchitectureInput", "CodeEntity", "Commit",
    "DEFAULT_LIMITS", "Dependency", "DependencyInput", "DocumentationInput", "FileAST",
    "GitHistory", "HistorySignals", "LimitExceeded", "MetricsInput", "OwnershipInput",
    "RepoFile", "StyleProfile", "TestingInput", "WalkResult", "analyze_ai_usage",
    "analyze_ai_utilization", "analyze_architecture", "analyze_dependencies",
    "analyze_documentation", "analyze_git_history", "analyze_metrics", "analyze_ownership",
    "analyze_testing", "build_import_graph", "classify", "classify_ai_usage", "classify_intent",
    "collect_history", "detect_language", "duplication_ratio", "find_readme", "hash_bytes",
    "heuristic_file_summary", "is_dependency_manifest", "is_programming_language", "is_test_path",
    "parse_file", "parse_dependencies", "profile_file", "should_ignore", "style_discontinuity",
    "supports_ast", "walk_repository",
]
