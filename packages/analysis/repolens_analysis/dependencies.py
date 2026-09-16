"""Dependency manifest analysis.

Reports what the project declares and how disciplined the declaration is.

It deliberately does **not** claim vulnerabilities. No offline vulnerability
database is bundled, and asserting a CVE without reliable data would be
fabricated evidence. The limitation is reported with every result.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp

ANALYZER_NAME = "dependencies"
ANALYZER_VERSION = "1.0.0"

#: Coarse technology categories used for job matching and Engineering DNA.
DEPENDENCY_CATEGORIES: dict[str, tuple[str, ...]] = {
    "web_backend": ("fastapi", "flask", "django", "express", "koa", "nestjs", "gin",
                    "spring-boot", "starlette", "hapi", "rails"),
    "web_frontend": ("react", "next", "vue", "svelte", "angular", "solid-js", "remix",
                     "tailwindcss", "vite"),
    "database": ("sqlalchemy", "prisma", "psycopg", "psycopg2", "pymongo", "mongoose",
                 "redis", "asyncpg", "typeorm", "sequelize", "alembic", "pgvector"),
    "ai_ml": ("torch", "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn",
              "transformers", "langchain", "llama-index", "llama_index", "openai",
              "anthropic", "sentence-transformers", "xgboost", "lightgbm", "spacy",
              "chromadb", "faiss-cpu", "faiss", "qdrant-client", "pinecone-client",
              "numpy", "pandas", "scipy", "datasets", "accelerate", "peft", "trl"),
    "testing": ("pytest", "jest", "vitest", "mocha", "chai", "playwright", "cypress",
                "unittest2", "testing-library", "junit", "hypothesis", "faker"),
    "devops": ("docker", "kubernetes", "boto3", "terraform", "ansible", "celery",
               "gunicorn", "uvicorn", "supervisor", "prometheus-client"),
    "security": ("cryptography", "pyjwt", "bcrypt", "passlib", "argon2-cffi",
                 "helmet", "jsonwebtoken", "oauthlib", "authlib"),
    "data_viz": ("matplotlib", "seaborn", "plotly", "recharts", "d3", "chart.js"),
    "http": ("requests", "httpx", "aiohttp", "axios", "node-fetch", "urllib3"),
}

_UNPINNED_SPEC_RE = re.compile(r"^[\^~>*]|^$|latest")
_PY_REQ_RE = re.compile(r"^\s*([A-Za-z0-9._\-\[\]]+)\s*([=<>!~]{1,2}\s*[^\s;#]+)?")


@dataclass(slots=True)
class DependencyInput:
    texts: dict[str, str]
    all_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Dependency:
    name: str
    version_spec: str
    ecosystem: str
    manifest: str
    dev: bool = False

    @property
    def pinned(self) -> bool:
        spec = self.version_spec.strip()
        if not spec:
            return False
        return not bool(_UNPINNED_SPEC_RE.match(spec))


def _parse_package_json(path: str, text: str) -> list[Dependency]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps: list[Dependency] = []
    for key, dev in (("dependencies", False), ("devDependencies", True),
                     ("peerDependencies", False)):
        for name, spec in (payload.get(key) or {}).items():
            deps.append(Dependency(name=name.lower(), version_spec=str(spec),
                                   ecosystem="npm", manifest=path, dev=dev))
    return deps


def _parse_requirements(path: str, text: str) -> list[Dependency]:
    deps: list[Dependency] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _PY_REQ_RE.match(line)
        if not match:
            continue
        name = match.group(1).split("[")[0].lower()
        deps.append(Dependency(name=name, version_spec=(match.group(2) or "").strip(),
                               ecosystem="pypi", manifest=path,
                               dev="dev" in path.lower() or "test" in path.lower()))
    return deps


def _parse_pyproject(path: str, text: str) -> list[Dependency]:
    try:
        payload = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    deps: list[Dependency] = []
    project = payload.get("project") or {}
    for spec in project.get("dependencies") or []:
        match = _PY_REQ_RE.match(str(spec))
        if match:
            deps.append(Dependency(name=match.group(1).split("[")[0].lower(),
                                   version_spec=(match.group(2) or "").strip(),
                                   ecosystem="pypi", manifest=path))
    for group, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs:
            match = _PY_REQ_RE.match(str(spec))
            if match:
                deps.append(Dependency(name=match.group(1).split("[")[0].lower(),
                                       version_spec=(match.group(2) or "").strip(),
                                       ecosystem="pypi", manifest=path,
                                       dev=group in ("dev", "test", "lint")))
    poetry = ((payload.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        version = spec if isinstance(spec, str) else str((spec or {}).get("version", ""))
        deps.append(Dependency(name=name.lower(), version_spec=version,
                               ecosystem="pypi", manifest=path))
    return deps


def _parse_cargo(path: str, text: str) -> list[Dependency]:
    try:
        payload = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    deps = []
    for key, dev in (("dependencies", False), ("dev-dependencies", True)):
        for name, spec in (payload.get(key) or {}).items():
            version = spec if isinstance(spec, str) else str((spec or {}).get("version", ""))
            deps.append(Dependency(name=name.lower(), version_spec=version,
                                   ecosystem="cargo", manifest=path, dev=dev))
    return deps


def _parse_gomod(path: str, text: str) -> list[Dependency]:
    deps = []
    for line in text.splitlines():
        match = re.match(r"\s*([\w./\-]+)\s+(v[\w.\-+]+)", line)
        if match and "module " not in line and "go " != line.strip()[:3]:
            deps.append(Dependency(name=match.group(1).lower(), version_spec=match.group(2),
                                   ecosystem="go", manifest=path))
    return deps


_PARSERS = {
    "package.json": _parse_package_json,
    "pyproject.toml": _parse_pyproject,
    "Cargo.toml": _parse_cargo,
    "go.mod": _parse_gomod,
}


def parse_dependencies(texts: dict[str, str]) -> list[Dependency]:
    deps: list[Dependency] = []
    for path, text in texts.items():
        name = path.rsplit("/", 1)[-1]
        if name in _PARSERS:
            deps.extend(_PARSERS[name](path, text))
        elif name.startswith("requirements") and name.endswith(".txt"):
            deps.extend(_parse_requirements(path, text))
    return deps


def categorize(deps: list[Dependency]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for dep in deps:
        for category, markers in DEPENDENCY_CATEGORIES.items():
            if any(dep.name == m or dep.name.startswith(f"{m}-") or dep.name.startswith(f"@{m}/")
                   or m in dep.name.split("/")[-1] for m in markers):
                result.setdefault(category, [])
                if dep.name not in result[category]:
                    result[category].append(dep.name)
    return result


def analyze_dependencies(data: DependencyInput) -> AnalyzerResult:
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    deps = parse_dependencies(data.texts)
    manifests = sorted({d.manifest for d in deps})
    lock_files = [p for p in data.all_paths
                  if p.rsplit("/", 1)[-1].lower() in
                  {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                   "uv.lock", "cargo.lock", "go.sum", "pipfile.lock", "composer.lock"}]

    if not deps:
        result.score = None
        result.partial = True
        result.confidence = 0.4
        result.metrics = {"dependency_count": 0, "manifests": [], "categories": {}}
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim="No dependency manifest was found",
            severity=Severity.LOW, confidence=0.8, supports="neutral", tags=("dependencies",),
            evidence=(EvidenceDetail(detail="no package.json, requirements.txt, pyproject.toml, "
                                            "go.mod or Cargo.toml detected"),),
        ))
        result.limit("dependencies", "No manifest to analyse; dependency signals are unavailable.")
        return result

    unique = {d.name for d in deps}
    runtime = [d for d in deps if not d.dev]
    unpinned = [d for d in deps if not d.pinned]
    categories = categorize(deps)

    pin_ratio = 1.0 - (len(unpinned) / len(deps))
    lock_score = 100.0 if lock_files else 35.0
    pin_score = 100.0 * pin_ratio
    # A very large runtime dependency surface for a small project is a
    # maintainability signal, not a defect; scored gently.
    size_score = 100.0 if len(runtime) <= 40 else clamp(100.0 - (len(runtime) - 40) * 0.8)
    score = 0.4 * pin_score + 0.35 * lock_score + 0.25 * size_score

    result.score = round(clamp(score), 2)
    result.confidence = 0.8
    result.metrics = {
        "dependency_count": len(deps),
        "unique_dependencies": len(unique),
        "runtime_dependencies": len(runtime),
        "dev_dependencies": len(deps) - len(runtime),
        "unpinned_dependencies": len(unpinned),
        "pinned_ratio": round(pin_ratio, 4),
        "manifests": manifests,
        "lock_files": lock_files,
        "ecosystems": sorted({d.ecosystem for d in deps}),
        "categories": categories,
        "dependency_names": sorted(unique)[:400],
    }

    result.add(Evidence(
        category=ScoreCategory.ARCHITECTURE,
        claim=f"{len(unique)} unique dependencies declared across {len(manifests)} manifest(s)",
        severity=Severity.INFO, confidence=0.9, supports="neutral", tags=("dependencies",),
        evidence=tuple(EvidenceDetail(detail=f"{sum(1 for d in deps if d.manifest == m)} entries", file=m)
                       for m in manifests[:5]),
    ))

    if categories:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim="Technology stack inferred from dependency manifests: "
                  + ", ".join(sorted(categories)),
            severity=Severity.INFO, confidence=0.85, supports="strength", tags=("dependencies", "stack"),
            evidence=tuple(EvidenceDetail(detail=f"{category}: {', '.join(names[:6])}")
                           for category, names in sorted(categories.items())),
        ))

    if not lock_files:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim="No lock file is committed, so builds are not reproducible",
            severity=Severity.MEDIUM, confidence=0.9, supports="weakness", tags=("dependencies", "reproducibility"),
            evidence=(EvidenceDetail(detail="no package-lock.json / poetry.lock / go.sum equivalent found"),),
        ))
    if unpinned:
        result.add(Evidence(
            category=ScoreCategory.ARCHITECTURE,
            claim=f"{len(unpinned)} dependency specifier(s) are unpinned or use floating ranges",
            severity=Severity.LOW, confidence=0.85, supports="weakness", tags=("dependencies",),
            evidence=tuple(EvidenceDetail(detail=f"{d.name} {d.version_spec or '(no version)'}", file=d.manifest)
                           for d in unpinned[:6]),
        ))

    result.limit(
        "vulnerabilities",
        "Known-vulnerability status is NOT reported. RepoLens does not bundle a CVE database, and "
        "claiming vulnerabilities without reliable advisory data would be fabricated evidence. "
        "Connect an advisory feed to enable this.",
    )
    return result
