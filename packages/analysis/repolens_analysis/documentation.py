"""Documentation analysis.

Scores the README and supporting documentation on the dimensions a reviewer
actually cares about: can somebody run this, understand its shape, and see what
its limits are?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repolens_shared import AnalyzerResult, Evidence, EvidenceDetail, ScoreCategory, Severity
from repolens_shared.textutils import clamp, truncate

ANALYZER_NAME = "documentation"
ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class DocFeature:
    key: str
    label: str
    weight: float
    patterns: tuple[str, ...]


#: Each feature is detected by heading/keyword patterns in the README (and, for
#: a few of them, by the presence of dedicated files).
DOC_FEATURES: tuple[DocFeature, ...] = (
    DocFeature("overview", "Project overview", 0.14,
               (r"^#\s+\S", r"\b(overview|about|what is|introduction)\b")),
    DocFeature("setup", "Setup / installation instructions", 0.20,
               (r"\b(installation|getting started|setup|quick ?start|prerequisites)\b",
                r"```(?:bash|sh|shell|console)")),
    DocFeature("usage", "Usage examples", 0.16,
               (r"\b(usage|example|how to use|running|run the)\b",)),
    DocFeature("architecture", "Architecture or design explanation", 0.14,
               (r"\b(architecture|design|how it works|system design|data flow|components)\b",)),
    DocFeature("api", "API documentation", 0.10,
               (r"\b(api|endpoint|route|openapi|swagger)\b", r"\b(GET|POST|PUT|DELETE)\s+/")),
    DocFeature("configuration", "Configuration / environment variables", 0.08,
               (r"\b(configuration|environment variable|\.env|config)\b",)),
    DocFeature("screenshots", "Screenshots or diagrams", 0.05,
               (r"!\[[^\]]*\]\([^)]+\)", r"```mermaid")),
    DocFeature("contributing", "Contribution instructions", 0.04,
               (r"\b(contributing|contribution|pull request)\b",)),
    DocFeature("limitations", "Known limitations or trade-offs", 0.05,
               (r"\b(limitation|known issue|caveat|trade-?off|not supported|roadmap|future work)\b",)),
    DocFeature("decisions", "Design decisions / rationale", 0.04,
               (r"\b(decision|why we|rationale|chose|instead of|adr)\b",)),
)

_README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme")
_PLACEHOLDER_RE = re.compile(
    r"(your[- ]project[- ]name|todo: (?:add|write)|lorem ipsum|"
    r"this project was bootstrapped with|"
    r"getting started with create[- ]react[- ]app|"
    r"^\s*#\s*(?:project|app|untitled)\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(slots=True)
class DocumentationInput:
    texts: dict[str, str]
    all_paths: list[str] = field(default_factory=list)
    documented_function_ratio: float = 0.0


def find_readme(texts: dict[str, str]) -> tuple[str | None, str]:
    for path, text in texts.items():
        if "/" not in path and path.lower() in _README_NAMES:
            return path, text
    for path, text in texts.items():
        if path.lower().endswith(_README_NAMES):
            return path, text
    return None, ""


def analyze_documentation(data: DocumentationInput) -> AnalyzerResult:
    result = AnalyzerResult(analyzer=ANALYZER_NAME, version=ANALYZER_VERSION)
    readme_path, readme = find_readme(data.texts)

    doc_files = [
        p for p in data.all_paths
        if p.lower().endswith((".md", ".rst")) and "node_modules" not in p
    ]
    supporting = [p for p in doc_files if p != readme_path]

    if not readme:
        result.score = 0.0
        result.confidence = 0.95
        result.metrics = {
            "has_readme": False, "readme_words": 0, "doc_files": len(doc_files),
            "features": {}, "placeholder_readme": False,
        }
        result.add(Evidence(
            category=ScoreCategory.DOCUMENTATION,
            claim="No README was found in the repository",
            severity=Severity.HIGH, confidence=0.95, supports="weakness", tags=("readme",),
            evidence=(EvidenceDetail(detail=f"{len(data.all_paths)} files inspected"),),
        ))
        return result

    lowered = readme.lower()
    features: dict[str, bool] = {}
    for feature in DOC_FEATURES:
        hit = any(re.search(p, readme, re.IGNORECASE | re.MULTILINE) for p in feature.patterns)
        if feature.key == "api" and not hit:
            hit = any("openapi" in p.lower() or "swagger" in p.lower() for p in data.all_paths)
        if feature.key == "contributing" and not hit:
            hit = any(p.lower().startswith("contributing") for p in data.all_paths)
        if feature.key == "architecture" and not hit:
            hit = any("architecture" in p.lower() for p in supporting)
        features[feature.key] = hit

    words = len(readme.split())
    placeholder = bool(_PLACEHOLDER_RE.search(readme))

    feature_score = 100.0 * sum(f.weight for f in DOC_FEATURES if features[f.key])
    # Length gate: a 30-word README cannot score highly even if it name-drops
    # every keyword.
    if words < 60:
        length_factor = 0.35
    elif words < 150:
        length_factor = 0.6
    elif words < 400:
        length_factor = 0.85
    else:
        length_factor = 1.0

    score = feature_score * length_factor
    if placeholder:
        score *= 0.55
    score += min(8.0, len(supporting) * 2.0)
    score += min(10.0, data.documented_function_ratio * 20.0)

    result.score = round(clamp(score), 2)
    result.confidence = 0.85
    result.metrics = {
        "has_readme": True,
        "readme_path": readme_path,
        "readme_words": words,
        "doc_files": len(doc_files),
        "supporting_docs": supporting[:20],
        "features": features,
        "placeholder_readme": placeholder,
        "documented_function_ratio": round(data.documented_function_ratio, 4),
        "feature_weights": {f.key: f.weight for f in DOC_FEATURES},
    }

    present = [f.label for f in DOC_FEATURES if features[f.key]]
    missing = [f.label for f in DOC_FEATURES if not features[f.key]]

    if present:
        result.add(Evidence(
            category=ScoreCategory.DOCUMENTATION,
            claim=f"README covers {len(present)} of {len(DOC_FEATURES)} documentation dimensions",
            severity=Severity.INFO, confidence=0.8, supports="strength", tags=("readme",),
            evidence=tuple(EvidenceDetail(detail=label, file=readme_path) for label in present[:8]),
        ))
    if missing:
        result.add(Evidence(
            category=ScoreCategory.DOCUMENTATION,
            claim=f"README is missing {len(missing)} documentation dimension(s)",
            severity=Severity.MEDIUM if len(missing) > 4 else Severity.LOW,
            confidence=0.8, supports="weakness", tags=("readme",),
            evidence=tuple(EvidenceDetail(detail=f"no {label.lower()} section detected", file=readme_path)
                           for label in missing[:8]),
        ))
    if placeholder:
        snippet = _PLACEHOLDER_RE.search(readme)
        result.add(Evidence(
            category=ScoreCategory.DOCUMENTATION,
            claim="README retains scaffold or placeholder text",
            severity=Severity.MEDIUM, confidence=0.8, supports="weakness",
            tags=("readme", "ownership_signal"),
            evidence=(EvidenceDetail(
                detail="generated-template text left in place", file=readme_path,
                snippet=truncate(snippet.group(0) if snippet else "", 120)),),
        ))
    if words < 60:
        result.add(Evidence(
            category=ScoreCategory.DOCUMENTATION,
            claim=f"README is very short ({words} words)",
            severity=Severity.MEDIUM, confidence=0.9, supports="weakness", tags=("readme",),
            evidence=(EvidenceDetail(detail="a reviewer cannot set the project up from this", file=readme_path),),
        ))

    result.limit(
        "documentation",
        "Documentation quality is assessed structurally (sections present, length, examples). "
        "The factual accuracy of the prose is not verified.",
    )
    return result
