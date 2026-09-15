"""Repository-specific interview questions and technical verification.

Questions are generated from the artefacts the analysis actually found: the most
complex function in this repository, the module everything imports, the security
finding on line 41, the dependency that carries the most risk. Generic questions
are emitted only when a repository yields nothing specific, and are labelled as
such.

Answer assessment is deterministic by default and can be enriched by an LLM.
Either way it produces a *verification score*, never a hiring outcome, and a
reviewer can override any individual assessment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from repolens_shared.textutils import clamp, tokenize_words

from app.services import llm

GENERATOR_VERSION = "1.0.0"

QUESTION_CATEGORIES = (
    "fundamentals", "architecture", "code_specific", "debugging",
    "performance", "security", "system_design", "ownership",
)

#: Dimensions an answer is assessed on, with their weight in the answer score.
ASSESSMENT_DIMENSIONS: dict[str, float] = {
    "technical_correctness": 0.30,
    "specificity": 0.22,
    "repository_consistency": 0.20,
    "depth_of_understanding": 0.18,
    "communication": 0.10,
}

_DEPTH_MARKERS = (
    "because", "trade-off", "tradeoff", "instead of", "alternative", "the reason",
    "otherwise", "which means", "so that", "in order to", "downside", "limitation",
    "we could", "i chose", "i decided", "considered", "compared",
)
_STRUCTURE_MARKERS = ("first", "second", "then", "finally", "however", "therefore", "for example")
_HEDGE_MARKERS = ("i don't know", "not sure", "no idea", "can't remember", "i forgot")


@dataclass(slots=True)
class GeneratedQuestion:
    category: str
    question: str
    difficulty: str
    rationale: str
    anchors: list[dict[str, Any]] = field(default_factory=list)
    expected_points: list[str] = field(default_factory=list)
    generated_by: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "question": self.question, "difficulty": self.difficulty,
            "rationale": self.rationale, "anchors": self.anchors,
            "expected_points": self.expected_points, "generated_by": self.generated_by,
            "generator_version": GENERATOR_VERSION,
        }


def generate_questions(
    analysis_results: dict[str, Any],
    repository_name: str,
    limit: int = 12,
) -> list[GeneratedQuestion]:
    """Build questions from a completed analysis.

    ``analysis_results`` is the stored per-analyzer output; every question must
    cite something inside it.
    """
    questions: list[GeneratedQuestion] = []
    metrics = (analysis_results.get("code_metrics") or {}).get("metrics") or {}
    architecture = (analysis_results.get("architecture") or {}).get("metrics") or {}
    security = (analysis_results.get("security") or {}).get("metrics") or {}
    testing = (analysis_results.get("testing") or {}).get("metrics") or {}
    dependencies = (analysis_results.get("dependencies") or {}).get("metrics") or {}
    git_history = (analysis_results.get("git_history") or {}).get("metrics") or {}
    ai_usage = (analysis_results.get("ai_usage") or {}).get("metrics") or {}
    similarity = (analysis_results.get("similarity") or {}).get("metrics") or {}
    evidence = [
        e for result in analysis_results.values()
        for e in (result.get("evidence") or [])
    ]

    questions.extend(_code_specific(metrics, evidence))
    questions.extend(_architecture(architecture))
    questions.extend(_debugging(security, metrics, evidence))
    questions.extend(_performance(metrics, dependencies, evidence))
    questions.extend(_security(security))
    questions.extend(_system_design(dependencies, architecture, repository_name))
    questions.extend(_testing_and_history(testing, git_history))
    questions.extend(_ownership(ai_usage, similarity, git_history))

    if not questions:
        questions.append(GeneratedQuestion(
            category="fundamentals",
            question=f"Walk me through what {repository_name} does and how its pieces fit together.",
            difficulty="easy",
            rationale="The analysis produced no repository-specific anchors, so this falls back to "
                      "an open question. Re-run the analysis if this is unexpected.",
            expected_points=["purpose of the project", "main components", "how data flows"],
            generated_by="fallback",
        ))
    return questions[:limit]


def _find_evidence(evidence: list[dict[str, Any]], tag: str) -> list[dict[str, Any]]:
    return [e for e in evidence if tag in (e.get("tags") or [])]


def _anchor_details(evidence_items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for item in evidence_items:
        for detail in item.get("evidence") or []:
            if detail.get("file"):
                anchors.append({
                    "file": detail["file"], "line": detail.get("line"),
                    "detail": detail.get("detail", ""), "metric": detail.get("metric"),
                })
            if len(anchors) >= limit:
                return anchors
    return anchors


def _code_specific(metrics: dict[str, Any], evidence: list[dict[str, Any]]) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    complexity_evidence = _find_evidence(evidence, "complexity")
    anchors = _anchor_details(complexity_evidence, limit=2)
    if anchors:
        anchor = anchors[0]
        symbol = _symbol_from(anchor["detail"])
        questions.append(GeneratedQuestion(
            category="code_specific",
            question=(
                f"`{symbol}` in `{anchor['file']}`"
                + (f" (line {anchor['line']})" if anchor.get("line") else "")
                + f" is the most complex function in this repository"
                + (f", with a cyclomatic complexity of {int(anchor['metric'])}" if anchor.get("metric") else "")
                + ". Walk me through what it does, and explain why it ended up this shape."
            ),
            difficulty="medium",
            rationale=f"Anchored on the highest-complexity function found by static analysis: {anchor['detail']}.",
            anchors=[anchor],
            expected_points=[
                "what the function is responsible for",
                "why the branching is necessary (or where it could be simplified)",
                "how it is tested or verified",
            ],
        ))
    long_functions = _find_evidence(evidence, "function_size")
    long_anchors = _anchor_details(long_functions, limit=1)
    if long_anchors:
        anchor = long_anchors[0]
        questions.append(GeneratedQuestion(
            category="code_specific",
            question=(
                f"`{_symbol_from(anchor['detail'])}` in `{anchor['file']}` is one of the longest "
                "functions here. If you had to split it into smaller pieces, where would the seams "
                "be and why there?"
            ),
            difficulty="medium",
            rationale=f"Anchored on a long function reported by the metrics analyzer: {anchor['detail']}.",
            anchors=[anchor],
            expected_points=["identifies cohesive responsibilities", "names concrete extractions",
                             "considers the effect on tests and callers"],
        ))
    duplication = metrics.get("duplication_ratio", 0.0)
    if duplication and duplication > 0.1:
        questions.append(GeneratedQuestion(
            category="code_specific",
            question=(
                f"About {duplication * 100:.0f}% of the code blocks in this repository are "
                "duplicated elsewhere in it. Where does that duplication come from, and which "
                "instances would you factor out first?"
            ),
            difficulty="medium",
            rationale="Anchored on the measured duplication ratio.",
            expected_points=["explains the origin of the duplication",
                             "distinguishes incidental from intentional repetition",
                             "proposes a concrete abstraction"],
        ))
    return questions


def _architecture(architecture: dict[str, Any]) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    depended = architecture.get("most_depended_on") or []
    if depended:
        top = depended[0]
        questions.append(GeneratedQuestion(
            category="architecture",
            question=(
                f"`{top['file']}` is imported by {top['importers']} other modules — more than "
                "anything else here. What is its responsibility, and how would you change its "
                "interface without breaking its callers?"
            ),
            difficulty="hard",
            rationale="Anchored on the most-depended-on module in the internal import graph.",
            anchors=[{"file": top["file"], "detail": f"imported by {top['importers']} modules"}],
            expected_points=["states a single clear responsibility",
                             "recognises the blast radius of a change",
                             "describes a migration or deprecation path"],
        ))
    layers = architecture.get("layers_detected") or []
    if layers:
        questions.append(GeneratedQuestion(
            category="architecture",
            question=(
                f"The repository separates {', '.join(l.replace('_', ' ') for l in layers[:4])}. "
                "What belongs in each layer, and what is the rule you use to decide where a new "
                "piece of logic goes?"
            ),
            difficulty="medium",
            rationale=f"Anchored on the layers detected in the directory structure: {layers}.",
            expected_points=["articulates the boundary rule", "gives a concrete example",
                             "acknowledges where the codebase currently breaks the rule"],
        ))
    else:
        questions.append(GeneratedQuestion(
            category="architecture",
            question=(
                "The analysis did not find a conventional layer separation in this repository. "
                "How is the code organised, and how would you restructure it if it doubled in size?"
            ),
            difficulty="medium",
            rationale="Anchored on the absence of recognisable layering in the file tree.",
            expected_points=["explains the current organisation",
                             "proposes a structure that scales",
                             "identifies what would break first"],
        ))
    cycles = architecture.get("import_cycles") or []
    if cycles:
        questions.append(GeneratedQuestion(
            category="architecture",
            question=f"There is a circular import chain: {cycles[0]}. How did it arise and how "
                     "would you break it?",
            difficulty="hard",
            rationale="Anchored on a cycle found in the internal import graph.",
            expected_points=["explains the coupling", "proposes an interface or inversion",
                             "considers the effect on module boundaries"],
        ))
    return questions


def _debugging(security: dict[str, Any], metrics: dict[str, Any],
               evidence: list[dict[str, Any]]) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    if metrics.get("error_handling_per_function", 1.0) < 0.05:
        questions.append(GeneratedQuestion(
            category="debugging",
            question=(
                "The analysis found almost no error handling in this codebase. Pick the most "
                "failure-prone operation in it — network, disk or user input — and tell me exactly "
                "what happens today when it fails, and what should happen."
            ),
            difficulty="medium",
            rationale="Anchored on the measured density of error-handling constructs.",
            expected_points=["names a specific operation", "traces the current failure path",
                             "proposes handling with a user-visible consequence"],
        ))
    anchors = _anchor_details(_find_evidence(evidence, "complexity"), limit=1)
    if anchors:
        anchor = anchors[0]
        questions.append(GeneratedQuestion(
            category="debugging",
            question=(
                f"Suppose `{anchor['file']}` starts returning wrong results in production for one "
                "class of input. Describe how you would find the cause, step by step, with the "
                "tooling this project actually has."
            ),
            difficulty="medium",
            rationale="Anchored on a real, complex file in the repository.",
            anchors=[anchor],
            expected_points=["reproduces before fixing", "uses logs, tests or a debugger concretely",
                             "narrows systematically rather than guessing"],
        ))
    return questions


def _performance(metrics: dict[str, Any], dependencies: dict[str, Any],
                 evidence: list[dict[str, Any]]) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    categories = dependencies.get("categories") or {}
    if "database" in categories:
        questions.append(GeneratedQuestion(
            category="performance",
            question=(
                f"This project uses {', '.join(categories['database'][:3])}. If one endpoint "
                "suddenly received 10,000 concurrent requests, where would it break first, and "
                "what would you measure to confirm that rather than assume it?"
            ),
            difficulty="hard",
            rationale=f"Anchored on the data dependencies declared in the manifests: {categories['database'][:3]}.",
            expected_points=["identifies a concrete bottleneck (pool, lock, N+1, single process)",
                             "names a metric to confirm it", "proposes a proportionate fix"],
        ))
    if "ai_ml" in categories:
        questions.append(GeneratedQuestion(
            category="performance",
            question=(
                f"The repository depends on {', '.join(categories['ai_ml'][:3])}. What dominates "
                "latency and cost in your pipeline, and what did you do — or would you do — about it?"
            ),
            difficulty="hard",
            rationale=f"Anchored on the ML dependencies found: {categories['ai_ml'][:3]}.",
            expected_points=["separates model time from I/O time",
                             "mentions batching, caching or a smaller model",
                             "quantifies rather than hand-waves"],
        ))
    return questions


def _security(security: dict[str, Any]) -> list[GeneratedQuestion]:
    findings = security.get("findings") or []
    if not findings:
        return [GeneratedQuestion(
            category="security",
            question="No hardcoded credentials were found in this repository. How do you manage "
                     "secrets for it in development and in deployment?",
            difficulty="easy",
            rationale="Anchored on the clean result of the secret scan.",
            expected_points=["environment variables or a secret manager",
                             "no secrets in git history", "rotation"],
        )]
    finding = max(findings, key=lambda f: float(f.get("confidence", 0)))
    return [GeneratedQuestion(
        category="security",
        question=(
            f"Static analysis flagged \"{finding['title']}\" in `{finding.get('file')}` at line "
            f"{finding.get('line')}. Is that a real problem in context? If it is, how would you fix "
            "it; if it is not, explain why the pattern is safe here."
        ),
        difficulty="hard",
        rationale=f"Anchored on a real finding: {finding['rule_id']} ({finding['severity']}).",
        anchors=[{"file": finding.get("file"), "line": finding.get("line"),
                  "detail": finding["title"]}],
        expected_points=["reads the code in context rather than reacting to the label",
                         "explains the exploit path or why there isn't one",
                         "proposes a specific remediation"],
    )]


def _system_design(dependencies: dict[str, Any], architecture: dict[str, Any],
                   repository_name: str) -> list[GeneratedQuestion]:
    frameworks = architecture.get("frameworks") or []
    categories = dependencies.get("categories") or {}
    if not frameworks and not categories:
        return []
    stack = ", ".join(frameworks[:3]) or ", ".join(
        name for names in categories.values() for name in names[:1]
    )
    questions = [GeneratedQuestion(
        category="system_design",
        question=(
            f"{repository_name} is built on {stack}. Why that choice over the obvious "
            "alternatives, and what would have to change for you to pick differently?"
        ),
        difficulty="medium",
        rationale=f"Anchored on the frameworks and dependencies actually present: {stack}.",
        expected_points=["gives a real reason, not a popularity argument",
                         "names a specific alternative", "states the conditions that would flip the decision"],
    )]
    if "database" in categories:
        questions.append(GeneratedQuestion(
            category="system_design",
            question=(
                f"Why did you choose {categories['database'][0]} for this project, and what "
                "would break if you swapped it for the alternative you considered?"
            ),
            difficulty="medium",
            rationale=f"Anchored on the database dependency found: {categories['database'][0]}.",
            expected_points=["explains the data model fit", "knows the operational cost",
                             "identifies what is coupled to the choice"],
        ))
    return questions


def _testing_and_history(testing: dict[str, Any], git_history: dict[str, Any]) -> list[GeneratedQuestion]:
    questions: list[GeneratedQuestion] = []
    if testing.get("test_cases"):
        questions.append(GeneratedQuestion(
            category="fundamentals",
            question=(
                f"There are {testing['test_cases']} test cases here"
                + (f" using {', '.join(testing.get('frameworks') or [])}" if testing.get("frameworks") else "")
                + ". Which part of this codebase is least covered, and what would you write next?"
            ),
            difficulty="medium",
            rationale=f"Anchored on the {testing['test_cases']} test cases counted by the analyzer.",
            expected_points=["knows where coverage is thin", "prioritises by risk not by ease",
                             "describes a concrete test"],
        ))
    else:
        questions.append(GeneratedQuestion(
            category="fundamentals",
            question="This repository has no automated tests. How did you verify that it works, "
                     "and what would you test first if you added a suite now?",
            difficulty="easy",
            rationale="Anchored on the absence of detected test cases.",
            expected_points=["describes the actual verification method used",
                             "picks a high-risk area to test first",
                             "shows awareness of what manual testing misses"],
        ))
    intents = git_history.get("intents") or {}
    if intents.get("fix"):
        questions.append(GeneratedQuestion(
            category="debugging",
            question=(
                f"The history contains {intents['fix']} bug-fix commits. Tell me about the hardest "
                "bug you fixed in this project: what was the symptom, what was the cause, and how "
                "did you find it?"
            ),
            difficulty="medium",
            rationale=f"Anchored on {intents['fix']} commits classified as fixes in the git history.",
            expected_points=["a specific, checkable story", "root cause not just the symptom",
                             "what they changed to prevent a recurrence"],
        ))
    return questions


def _ownership(ai_usage: dict[str, Any], similarity: dict[str, Any],
               git_history: dict[str, Any]) -> list[GeneratedQuestion]:
    """Ownership questions.

    Phrased as invitations to explain, never as accusations: AI-assisted
    development is legitimate, and the goal is to understand what the candidate
    knows about their own code.
    """
    questions: list[GeneratedQuestion] = []
    likelihood = ai_usage.get("estimated_ai_assistance")
    if likelihood is not None and likelihood >= 45:
        questions.append(GeneratedQuestion(
            category="ownership",
            question=(
                "Which parts of this project did you use AI assistance for, and what did you change "
                "about what it produced? Using AI is completely fine — I'm interested in how you "
                "worked with it."
            ),
            difficulty="easy",
            rationale=(
                f"Repository signals put AI-assistance likelihood at {likelihood:.0f}/100 "
                f"({ai_usage.get('confidence_band', 'unknown')} confidence). This is a "
                "probabilistic estimate, so the question invites explanation rather than asserting "
                "anything."
            ),
            expected_points=["specific about which parts and which tools",
                             "describes reviewing or modifying the output",
                             "can explain the generated code's behaviour"],
        ))
    external = similarity.get("external_matches") or []
    if external:
        match = external[0]
        questions.append(GeneratedQuestion(
            category="ownership",
            question=(
                f"`{match.get('symbol')}` in `{match.get('file')}` is very close to code in another "
                "repository we have analysed. Where did that implementation come from — shared "
                "library, common tutorial, your own earlier project?"
            ),
            difficulty="medium",
            rationale=f"Anchored on a cross-repository similarity of {match.get('similarity')}.",
            anchors=[{"file": match.get("file"), "detail": f"similarity {match.get('similarity')}"}],
            expected_points=["gives a straightforward provenance answer",
                             "can explain how the code works regardless of origin"],
        ))
    if git_history.get("largest_commit_share", 0) > 0.7:
        questions.append(GeneratedQuestion(
            category="ownership",
            question=(
                f"Most of this repository arrived in a single commit "
                f"({git_history['largest_commit_share'] * 100:.0f}% of all changed lines). "
                "What did the development process actually look like before that commit?"
            ),
            difficulty="easy",
            rationale="Anchored on the commit-size distribution in the git history. Importing "
                      "existing work in one commit is normal; the question just asks for context.",
            expected_points=["a coherent account of how it was built",
                             "consistent with what the code shows"],
        ))
    return questions


def _symbol_from(detail: str) -> str:
    match = re.search(r"`([^`]+)`", detail)
    return match.group(1) if match else "this function"


# -- answer assessment --------------------------------------------------------

def assess_answer(
    question: dict[str, Any], answer_text: str, repository_facts: dict[str, Any],
) -> dict[str, Any]:
    """Assess one answer.

    The deterministic path measures observable properties of the text: does it
    cover the expected points, does it reference real repository artefacts, does
    it explain causally, is it structured. That is a weak proxy for understanding
    and is labelled as such; an LLM assessment (when configured) and the
    reviewer's own score both override it.
    """
    text = (answer_text or "").strip()
    words = tokenize_words(text)
    word_count = len(words)

    if word_count < 5:
        return {
            "score": 0.0,
            "dimensions": {k: {"score": 0.0, "detail": "The answer is empty or too short to assess."}
                           for k in ASSESSMENT_DIMENSIONS},
            "assessed_by": "deterministic",
            "limitation": "No substantive answer was provided.",
        }

    expected = [p.lower() for p in question.get("expected_points") or []]
    lowered = text.lower()
    covered = [
        point for point in expected
        if _covers(lowered, words, point)
    ]
    correctness = 100.0 * (len(covered) / len(expected)) if expected else 55.0

    anchors = question.get("anchors") or []
    anchor_terms = {
        term.lower()
        for anchor in anchors
        for term in (
            [str(anchor.get("file", "")).split("/")[-1]]
            + re.findall(r"`([^`]+)`", str(anchor.get("detail", "")))
        )
        if term
    }
    repo_terms = {str(t).lower() for t in (repository_facts.get("symbols") or [])[:400]}
    repo_terms |= {str(t).lower().split("/")[-1] for t in (repository_facts.get("files") or [])[:400]}
    referenced = {t for t in anchor_terms | repo_terms if t and t in lowered}
    specificity = clamp(
        30.0 * len(referenced & anchor_terms) + 12.0 * len(referenced - anchor_terms)
        + (18.0 if re.search(r"`[^`]+`|\w+\.\w{1,4}\b|line \d+", text) else 0.0)
    )

    # Repository consistency: does the answer contradict a measured fact?
    consistency, consistency_detail = _consistency(lowered, repository_facts)

    depth_hits = sum(1 for marker in _DEPTH_MARKERS if marker in lowered)
    hedges = sum(1 for marker in _HEDGE_MARKERS if marker in lowered)
    depth = clamp(min(100.0, depth_hits * 18.0 + min(40.0, word_count / 4.0)) - hedges * 25.0)

    structure_hits = sum(1 for marker in _STRUCTURE_MARKERS if marker in lowered)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    avg_sentence = word_count / sentences
    communication = clamp(
        45.0 + structure_hits * 10.0
        + (20.0 if 8 <= avg_sentence <= 30 else 0.0)
        + (10.0 if word_count >= 40 else 0.0)
    )

    dimensions = {
        "technical_correctness": {
            "score": round(correctness, 1),
            "detail": (f"Covered {len(covered)} of {len(expected)} expected points."
                       if expected else "No expected points were recorded for this question."),
        },
        "specificity": {
            "score": round(specificity, 1),
            "detail": (f"References {len(referenced)} concrete repository artefact(s)."
                       if referenced else "The answer does not reference any specific file, "
                                          "symbol or line from the repository."),
        },
        "repository_consistency": {"score": round(consistency, 1), "detail": consistency_detail},
        "depth_of_understanding": {
            "score": round(depth, 1),
            "detail": f"{depth_hits} causal or trade-off statement(s) in {word_count} words"
                      + (f"; {hedges} explicit uncertainty marker(s)." if hedges else "."),
        },
        "communication": {
            "score": round(communication, 1),
            "detail": f"{sentences} sentence(s), average {avg_sentence:.0f} words per sentence.",
        },
    }
    score = sum(dimensions[k]["score"] * w for k, w in ASSESSMENT_DIMENSIONS.items())

    assessment = {
        "score": round(clamp(score), 1),
        "dimensions": dimensions,
        "weights": ASSESSMENT_DIMENSIONS,
        "assessed_by": "deterministic",
        "limitation": (
            "This assessment measures coverage, specificity and structure in the text. It cannot "
            "judge whether an explanation is technically correct. Treat it as preparation for the "
            "reviewer's own judgement, which overrides it."
        ),
    }

    if llm.is_available():
        enriched = _llm_assessment(question, text, repository_facts, assessment)
        if enriched:
            return enriched
    return assessment


def _covers(lowered: str, words: list[str], point: str) -> bool:
    """A point counts as covered when most of its content words appear."""
    point_words = [w for w in tokenize_words(point) if len(w) > 3]
    if not point_words:
        return point in lowered
    hits = sum(1 for w in point_words if w in words or w in lowered)
    return hits >= max(1, len(point_words) // 2)


def _consistency(lowered: str, facts: dict[str, Any]) -> tuple[float, str]:
    """Check the answer against a few hard facts from the analysis."""
    contradictions: list[str] = []
    if facts.get("test_cases") == 0 and re.search(r"\b(we|i) (have|wrote|added) (unit )?tests\b", lowered):
        contradictions.append("claims tests exist, but no test cases were detected")
    if not facts.get("ci_runs_tests") and "ci runs" in lowered:
        contradictions.append("claims CI runs tests, but no test invocation was found in CI config")
    languages = {str(l).lower() for l in (facts.get("languages") or [])}
    claimed = {
        language for language in ("python", "typescript", "javascript", "java", "go", "rust")
        if re.search(rf"\bwritten in {language}\b", lowered)
    }
    unsupported = claimed - languages
    if unsupported:
        contradictions.append(
            f"refers to {', '.join(sorted(unsupported))}, which was not detected in this repository"
        )
    if contradictions:
        return clamp(100.0 - 35.0 * len(contradictions)), "; ".join(contradictions)
    return 80.0, "No contradictions with the measured repository facts were found."


def _llm_assessment(
    question: dict[str, Any], answer: str, facts: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any] | None:
    response = llm.complete(
        llm.evidence_prompt(
            task="Assess a candidate's answer to a repository-specific technical question.",
            evidence={
                "question": question.get("question"),
                "expected_points": question.get("expected_points"),
                "anchors": question.get("anchors"),
                "repository_facts": facts,
                "candidate_answer": answer[:6000],
                "deterministic_assessment": baseline["dimensions"],
            },
            instructions=(
                "Return strict JSON only, no prose, with this shape: "
                '{"technical_correctness": {"score": 0-100, "detail": "..."}, '
                '"specificity": {...}, "repository_consistency": {...}, '
                '"depth_of_understanding": {...}, "communication": {...}, '
                '"summary": "two sentences"}. '
                "Judge only against the evidence given. Do not recommend a hiring decision."
            ),
        ),
        max_tokens=900,
    )
    if response.generated_by != "llm" or not response.text:
        return None
    import json

    try:
        payload = json.loads(re.sub(r"^```(?:json)?|```$", "", response.text.strip(), flags=re.M))
    except (ValueError, TypeError):
        return None
    dimensions: dict[str, Any] = {}
    for key in ASSESSMENT_DIMENSIONS:
        item = payload.get(key)
        if not isinstance(item, dict) or not isinstance(item.get("score"), (int, float)):
            return None
        dimensions[key] = {"score": clamp(float(item["score"])), "detail": str(item.get("detail", ""))[:400]}
    return {
        "score": round(sum(dimensions[k]["score"] * w for k, w in ASSESSMENT_DIMENSIONS.items()), 1),
        "dimensions": dimensions,
        "weights": ASSESSMENT_DIMENSIONS,
        "assessed_by": "llm",
        "model": response.model,
        "summary": str(payload.get("summary", ""))[:600],
        "deterministic_baseline": baseline["dimensions"],
        "limitation": (
            "A language model assessed this answer against the supplied evidence. It is an aid to "
            "the reviewer, not a substitute for their judgement, and the reviewer's score overrides it."
        ),
    }


def session_score(answer_scores: list[float]) -> float | None:
    return round(sum(answer_scores) / len(answer_scores), 2) if answer_scores else None
