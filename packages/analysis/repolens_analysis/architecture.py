"""Architecture analysis.

Derives structure from the file tree and the import graph:

* Is there a recognisable layering (routes / services / models / components)?
* How coupled are the modules, and are there import cycles?
* Is the project a single-file script, a flat pile of files, or a composed system?

The import graph is built from AST import statements resolved against the
repository's own files, so third-party imports do not inflate coupling.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp, scale

from .ast_engine import FileAST
from .classification import is_test_path

ANALYZER_NAME = "architecture"
ANALYZER_VERSION = "1.0.0"

#: Directory-name conventions that indicate a deliberate layer.
LAYER_MARKERS: dict[str, tuple[str, ...]] = {
    "api_layer": ("api", "routes", "routers", "controllers", "endpoints", "handlers", "views"),
    "service_layer": ("services", "service", "usecases", "use_cases", "domain", "core",
                      "business", "logic", "managers"),
    "data_layer": ("models", "entities", "schemas", "repositories", "repository", "dao",
                   "db", "database", "store", "persistence", "migrations"),
    "presentation": ("components", "pages", "app", "ui", "views", "screens", "templates",
                     "widgets", "features"),
    "shared": ("utils", "helpers", "lib", "common", "shared", "config", "constants", "types"),
    "tests": ("tests", "test", "__tests__", "spec", "e2e"),
    "infrastructure": ("infrastructure", "infra", "deploy", "docker", "k8s", "terraform",
                       "ops", ".github"),
    "workers": ("workers", "worker", "tasks", "jobs", "queue", "celery", "consumers"),
}

FRAMEWORK_MARKERS: dict[str, tuple[str, ...]] = {
    "fastapi": ("from fastapi", "import fastapi", "FastAPI("),
    "flask": ("from flask", "Flask(__name__)"),
    "django": ("from django", "django.db", "INSTALLED_APPS"),
    "express": ("require('express')", 'from "express"', "express()"),
    "nestjs": ("@nestjs/common", "@Module("),
    "next": ("next/router", "next/link", "next/navigation", '"next"'),
    "react": ("from 'react'", 'from "react"', "React."),
    "vue": ("from 'vue'", "<template>"),
    "spring": ("org.springframework", "@SpringBootApplication"),
    "pytorch": ("import torch", "from torch"),
    "tensorflow": ("import tensorflow", "from tensorflow"),
    "langchain": ("from langchain", "import langchain"),
}

ARCHITECTURE_WEIGHTS = {
    "layering": 0.32,
    "modularity": 0.24,
    "coupling": 0.22,
    "structure_depth": 0.12,
    "entry_points": 0.10,
}

_PY_IMPORT_RE = re.compile(r"^(?:from\s+([\w.]+)|import\s+([\w.]+))")
_JS_IMPORT_RE = re.compile(r"""from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]""")


@dataclass(slots=True)
class ArchitectureInput:
    asts: list[FileAST]
    all_paths: list[str]
    texts: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)


def _module_key(path: str) -> str:
    return re.sub(r"\.(py|js|jsx|ts|tsx|java|go|rb|c|cpp|h)$", "", path)


def build_import_graph(asts: list[FileAST]) -> dict[str, set[str]]:
    """Map file -> set of *internal* files it imports.

    Resolution is by suffix matching of the imported module path against
    repository files; unresolved imports are treated as third-party and dropped.
    """
    modules = {_module_key(a.path): a.path for a in asts}
    index: dict[str, list[str]] = defaultdict(list)
    for key, path in modules.items():
        parts = key.split("/")
        for depth in range(1, min(4, len(parts)) + 1):
            index["/".join(parts[-depth:])].append(path)
        index[parts[-1]].append(path)
    # When several files could satisfy an import, prefer the one a reader would
    # mean: real source over test fixtures, and the shallowest path. Without this
    # a fixture such as tests/apps/inner/flask.py absorbs every `import flask`.
    for key, candidates in index.items():
        index[key] = sorted(
            dict.fromkeys(candidates),
            key=lambda p: (is_test_path(p), p.count("/"), len(p), p),
        )

    graph: dict[str, set[str]] = {a.path: set() for a in asts}
    for file_ast in asts:
        for statement in file_ast.imports:
            targets: list[str] = []
            py = _PY_IMPORT_RE.match(statement.strip())
            if py:
                targets.append((py.group(1) or py.group(2) or "").replace(".", "/"))
            for match in _JS_IMPORT_RE.finditer(statement):
                targets.append((match.group(1) or match.group(2) or ""))
            for target in targets:
                target = target.strip().strip("/")
                if not target:
                    continue
                if target.startswith("."):
                    base = "/".join(file_ast.path.split("/")[:-1])
                    target = _normalise_relative(base, target)
                candidates = index.get(target) or index.get(target.split("/")[-1]) or []
                for candidate in candidates:
                    if candidate != file_ast.path:
                        graph[file_ast.path].add(candidate)
                        break
    return graph


def _normalise_relative(base: str, target: str) -> str:
    parts = base.split("/") if base else []
    for segment in target.split("/"):
        if segment == "." or segment == "":
            continue
        if segment == "..":
            if parts:
                parts.pop()
        else:
            parts.append(segment)
    return "/".join(parts)


def find_cycles(graph: dict[str, set[str]], limit: int = 10) -> list[list[str]]:
    """Depth-first cycle detection over the internal import graph."""
    cycles: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        if len(cycles) >= limit:
            return
        state[node] = 1
        stack.append(node)
        for neighbour in sorted(graph.get(node, ())):
            if state.get(neighbour, 0) == 0:
                visit(neighbour)
            elif state.get(neighbour) == 1 and len(cycles) < limit:
                index = stack.index(neighbour) if neighbour in stack else 0
                cycles.append([*stack[index:], neighbour])
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            visit(node)
    return cycles


def analyze_architecture(data: ArchitectureInput) -> AnalyzerResult:
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    source_paths = [
        p for p, c in data.categories.items()
        if c in ("CANDIDATE_CODE", "TEST_CODE")
    ] or [a.path for a in data.asts]

    directories = {"/".join(p.split("/")[:-1]) for p in source_paths if "/" in p}
    dir_names = {segment.lower() for d in directories for segment in d.split("/") if segment}
    layers = {
        layer: sorted(dir_names & set(markers))
        for layer, markers in LAYER_MARKERS.items()
    }
    present_layers = [layer for layer, hits in layers.items() if hits]

    depths = [p.count("/") for p in source_paths] or [0]
    max_depth = max(depths)
    avg_depth = sum(depths) / len(depths)
    root_files = sum(1 for p in source_paths if "/" not in p)

    graph = build_import_graph(data.asts)
    edges = sum(len(v) for v in graph.values())
    nodes = max(1, len(graph))
    fan_out = edges / nodes
    hubs = sorted(graph.items(), key=lambda kv: -len(kv[1]))[:5]
    in_degree: dict[str, int] = defaultdict(int)
    for targets in graph.values():
        for target in targets:
            in_degree[target] += 1
    cycles = find_cycles(graph)

    frameworks = sorted({
        name for name, markers in FRAMEWORK_MARKERS.items()
        for text in data.texts.values() if any(m in text for m in markers)
    })

    entry_points = sorted({
        p for p in data.all_paths
        if p.rsplit("/", 1)[-1] in ("main.py", "app.py", "manage.py", "index.js", "index.ts",
                                    "server.js", "server.ts", "main.go", "Main.java", "cli.py")
        or p in ("docker-compose.yml", "Dockerfile", "Makefile")
    })

    # --- sub-scores ----------------------------------------------------------
    core_layers = [l for l in present_layers if l not in ("tests", "shared")]
    layering = scale(float(len(core_layers)), 0.0, 4.0)
    file_count = max(1, len(source_paths))
    # Modularity: are files distributed across directories rather than piled at root?
    # `scale` maps the *root-level ratio* from worst (0.9 = everything at root)
    # to best (0.15 = only entry points at root).
    root_ratio = root_files / file_count
    modularity = scale(root_ratio, 0.9, 0.15) if file_count > 3 else 55.0
    # Coupling: moderate fan-out is healthy; very high fan-out or cycles are not.
    coupling = clamp(100.0 - max(0.0, fan_out - 4.0) * 12.0 - len(cycles) * 10.0)
    depth_score = scale(avg_depth, 0.0, 2.0) if max_depth else 20.0
    entry_score = 100.0 if entry_points else 40.0

    subs = {
        "layering": layering, "modularity": modularity, "coupling": coupling,
        "structure_depth": depth_score, "entry_points": entry_score,
    }
    score = sum(subs[k] * w for k, w in ARCHITECTURE_WEIGHTS.items())

    result.score = round(clamp(score), 2)
    result.confidence = 0.75 if data.asts else 0.35
    result.metrics = {
        "source_files": len(source_paths),
        "directories": len(directories),
        "max_depth": max_depth,
        "avg_depth": round(avg_depth, 2),
        "root_level_files": root_files,
        "layers_detected": present_layers,
        "layer_directories": {k: v for k, v in layers.items() if v},
        "frameworks": frameworks,
        "entry_points": entry_points[:20],
        "import_edges": edges,
        "avg_internal_imports_per_file": round(fan_out, 2),
        "import_cycles": [" → ".join(c) for c in cycles[:5]],
        "most_connected": [{"file": f, "imports": len(t)} for f, t in hubs if t],
        "most_depended_on": [{"file": f, "importers": n}
                             for f, n in sorted(in_degree.items(), key=lambda kv: -kv[1])[:5]],
        "sub_scores": {k: round(v, 2) for k, v in subs.items()},
        "weights": ARCHITECTURE_WEIGHTS,
    }

    if core_layers:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"Recognisable layering: {', '.join(l.replace('_', ' ') for l in core_layers)}",
            severity=Severity.INFO, confidence=0.75, supports="strength", tags=("layering",),
            evidence=tuple(
                EvidenceDetail(detail=f"{layer.replace('_', ' ')}: {', '.join(layers[layer])}")
                for layer in core_layers[:6]
            ),
        ))
    else:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim="No conventional layer separation was detected in the directory structure",
            severity=Severity.MEDIUM, confidence=0.65, supports="weakness", tags=("layering",),
            evidence=(EvidenceDetail(
                detail=f"{len(directories)} source directories, none matching common "
                       "api/service/model/component conventions"),),
        ))

    if root_files > max(5, file_count * 0.5):
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"{root_files} of {file_count} source files sit at the repository root",
            severity=Severity.MEDIUM, confidence=0.85, supports="weakness", tags=("modularity",),
            evidence=(EvidenceDetail(detail="flat structures become hard to navigate as a project grows"),),
        ))

    if cycles:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"{len(cycles)} circular import chain(s) detected between modules",
            severity=Severity.MEDIUM, confidence=0.8, supports="weakness", tags=("coupling",),
            evidence=tuple(EvidenceDetail(detail=" → ".join(c)) for c in cycles[:4]),
        ))

    if frameworks:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"Frameworks in use: {', '.join(frameworks)}",
            severity=Severity.INFO, confidence=0.85, supports="neutral", tags=("stack",),
            evidence=tuple(EvidenceDetail(detail=f"{name} usage detected in source") for name in frameworks[:6]),
        ))

    if hubs and hubs[0][1]:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"Internal coupling averages {fan_out:.1f} internal imports per file",
            severity=Severity.INFO if fan_out < 6 else Severity.MEDIUM,
            confidence=0.7, supports="strength" if fan_out < 6 else "weakness", tags=("coupling",),
            evidence=tuple(EvidenceDetail(detail=f"imports {len(targets)} internal modules", file=path)
                           for path, targets in hubs[:4] if targets),
        ))

    if not data.asts:
        result.partial = True
        result.limit("architecture",
                     "No parsed source files were available, so the import graph could not be built; "
                     "structure was assessed from the file tree alone.")
    result.limit(
        "architecture_inference",
        "Layering is inferred from directory naming conventions and the internal import graph. "
        "A well-designed project using unconventional names may be under-credited here.",
    )
    return result
