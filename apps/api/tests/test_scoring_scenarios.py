"""The scoring scenarios from the product specification.

These are the tests that matter most: they check that RepoLens reaches the
*right judgement* on four deliberately different repositories, not merely that
it produces a number.
"""

from __future__ import annotations

import pytest

from repolens_analysis import (
    AIUsageInput,
    ArchitectureInput,
    DependencyInput,
    DocumentationInput,
    MetricsInput,
    OwnershipInput,
    TestingInput,
    analyze_ai_usage,
    analyze_ai_utilization,
    analyze_architecture,
    analyze_dependencies,
    analyze_documentation,
    analyze_git_history,
    analyze_metrics,
    analyze_ownership,
    analyze_testing,
    collect_history,
    parse_file,
    profile_file,
    style_discontinuity,
    walk_repository,
)
from repolens_shared import AIUsageClassification, OriginalityClassification
from repolens_similarity import SimilarityInput, analyze_similarity

from tests.fixtures import BUILDERS


class Analysis:
    """Runs the analyzers over a synthetic repository, without the database."""

    def __init__(self, path):
        walk = walk_repository(path)
        self.texts = {f.path: f.text for f in walk.files if f.text is not None}
        self.categories = {f.path: str(f.category) for f in walk.files}
        self.languages = {f.path: f.language for f in walk.files}
        self.paths = [f.path for f in walk.files]
        self.asts = [
            parse_file(f.path, f.text, f.language or "text", keep_source=True)
            for f in walk.files
            if f.text is not None and f.is_source
        ]

        self.metrics = analyze_metrics(MetricsInput(asts=self.asts, texts=self.texts))
        self.testing = analyze_testing(TestingInput(
            texts=self.texts, categories=self.categories, asts=self.asts, all_paths=self.paths,
        ))
        self.documentation = analyze_documentation(DocumentationInput(
            texts=self.texts, all_paths=self.paths,
            documented_function_ratio=float(self.metrics.metrics.get("documented_function_ratio", 0)),
        ))
        self.dependencies = analyze_dependencies(DependencyInput(
            texts=self.texts, all_paths=self.paths,
        ))
        self.architecture = analyze_architecture(ArchitectureInput(
            asts=self.asts, all_paths=self.paths, texts=self.texts, categories=self.categories,
        ))
        self.git, self.history = analyze_git_history(collect_history(path))
        self.similarity, self.chunks = analyze_similarity(SimilarityInput(
            asts=self.asts, texts=self.texts, categories=self.categories, repository_id="test",
        ))

        profiles = [
            profile_file(a, self.texts[a.path])
            for a in self.asts
            if a.path in self.texts and self.categories.get(a.path) == "CANDIDATE_CODE"
        ]
        discontinuity, _ = style_discontinuity(profiles)

        self.ownership_input = OwnershipInput(
            history=self.history,
            test_cases=int(self.testing.metrics.get("test_cases", 0)),
            test_files=int(self.testing.metrics.get("test_files", 0)),
            references_own_modules=True,
            readme_words=int(self.documentation.metrics.get("readme_words", 0)),
            readme_is_placeholder=bool(self.documentation.metrics.get("placeholder_readme")),
            readme_features=sum(
                1 for v in (self.documentation.metrics.get("features") or {}).values() if v
            ),
            style_discontinuity=discontinuity,
            documented_function_ratio=float(
                self.metrics.metrics.get("documented_function_ratio", 0)
            ),
            source_file_count=sum(
                1 for c in self.categories.values() if c == "CANDIDATE_CODE"
            ),
            architecture_score=self.architecture.score,
            import_cycles=len(self.architecture.metrics.get("import_cycles") or []),
            ci_runs_tests=bool(self.testing.metrics.get("ci_runs_tests")),
            error_handling_per_function=float(
                self.metrics.metrics.get("error_handling_per_function", 0)
            ),
            dependency_score=self.dependencies.score,
            documentation_score=self.documentation.score,
        )
        self.ownership = analyze_ownership(self.ownership_input)
        self.ai_usage = analyze_ai_usage(
            AIUsageInput(
                asts=self.asts, texts=self.texts, categories=self.categories,
                history=self.history,
                duplication_ratio=float(self.metrics.metrics.get("duplication_ratio", 0)),
                structural_clone_groups=len(
                    self.similarity.metrics.get("structural_clone_groups") or []
                ),
                documented_function_ratio=float(
                    self.metrics.metrics.get("documented_function_ratio", 0)
                ),
                readme_words=int(self.documentation.metrics.get("readme_words", 0)),
                test_cases=int(self.testing.metrics.get("test_cases", 0)),
            ),
            ownership_confidence=self.ownership.score,
        )
        self.ownership_input.ai_likelihood = float(
            self.ai_usage.metrics["estimated_ai_assistance"]
        )
        self.utilization = analyze_ai_utilization(self.ownership_input, self.ownership.score or 0)


@pytest.fixture(scope="module")
def analyses(tmp_path_factory) -> dict[str, Analysis]:
    root = tmp_path_factory.mktemp("repositories")
    return {name: Analysis(builder(root)) for name, builder in BUILDERS.items()}


# -- Repository A: excellent engineering -------------------------------------

def test_excellent_repository_scores_high_quality(analyses):
    result = analyses["excellent"]
    assert result.metrics.score is not None and result.metrics.score >= 70, (
        f"technical quality {result.metrics.score}"
    )
    assert result.testing.score >= 60, f"testing {result.testing.score}"
    assert result.documentation.score >= 60, f"documentation {result.documentation.score}"


def test_excellent_repository_shows_high_ownership(analyses):
    result = analyses["excellent"]
    assert result.ownership.score >= 70, f"ownership {result.ownership.score}"
    assert result.history.evolution_score >= 60, f"evolution {result.history.evolution_score}"
    # Iteration after the first version is the core ownership signal.
    assert {"bug_fixes", "refactoring", "testing"} <= set(result.history.phases_present)


def test_excellent_repository_has_low_ai_likelihood(analyses):
    result = analyses["excellent"]
    likelihood = result.ai_usage.metrics["estimated_ai_assistance"]
    assert likelihood < 50, f"assistance likelihood {likelihood}"
    assert result.ai_usage.metrics["classification"] in (
        str(AIUsageClassification.AI_ASSISTED),
        str(AIUsageClassification.AI_AUGMENTED),
    )


# -- Repository B: large drop with no development history --------------------

def test_dropped_repository_has_weak_ownership(analyses):
    result = analyses["dropped"]
    assert result.ownership.score < 50, f"ownership {result.ownership.score}"


def test_dropped_repository_raises_assistance_signals(analyses):
    result = analyses["dropped"]
    likelihood = result.ai_usage.metrics["estimated_ai_assistance"]
    assert likelihood > analyses["excellent"].ai_usage.metrics["estimated_ai_assistance"]
    firing = [s for s in result.ai_usage.metrics["signals"] if s["strength"] > 0.3]
    assert any(s["id"] == "history_shape" for s in firing)


def test_dropped_repository_never_asserts_ai_authorship(analyses):
    """Whatever the signals say, the output must stay probabilistic."""
    result = analyses["dropped"]
    text = " ".join(
        [e.claim for e in result.ai_usage.evidence]
        + [d.detail for e in result.ai_usage.evidence for d in e.evidence]
    ).lower()
    for forbidden in ("was written by", "ai-generated code", "definitely", "proves", "cheat"):
        assert forbidden not in text, f"found '{forbidden}' in AI-usage output"
    assert any("probabilistic" in l.detail.lower() for l in result.ai_usage.limitations)


# -- Repository C: tutorial-derived ------------------------------------------

def test_tutorial_repository_is_detected(analyses):
    result = analyses["tutorial"]
    assert result.similarity.metrics["originality"] in (
        str(OriginalityClassification.STRONG_TUTORIAL_SIMILARITY),
        str(OriginalityClassification.POSSIBLY_TUTORIAL_DERIVED),
    )
    signals = {s["id"] for s in result.similarity.metrics["tutorial_signals"]}
    assert "next_scaffold" in signals


def test_tutorial_language_is_not_accusatory(analyses):
    result = analyses["tutorial"]
    text = " ".join(e.claim for e in result.similarity.evidence).lower()
    for forbidden in ("cheat", "plagiari", "dishonest", "fake", "fraud"):
        assert forbidden not in text
    assert "explanation is recommended" in text or "unmodified" in text


# -- Repository D: strong assistance signals, strong ownership ---------------

def test_augmented_repository_keeps_ownership_despite_ai_signals(analyses):
    result = analyses["augmented"]
    likelihood = result.ai_usage.metrics["estimated_ai_assistance"]
    assert result.ownership.score >= 60, f"ownership {result.ownership.score}"
    assert result.ai_usage.metrics["classification"] in (
        str(AIUsageClassification.AI_ASSISTED),
        str(AIUsageClassification.AI_AUGMENTED),
    ), f"classification with likelihood {likelihood}"


def test_augmented_repository_is_not_punished_for_ai_use(analyses):
    """The central product rule: legitimate AI use must not lower the score."""
    augmented = analyses["augmented"]
    dropped = analyses["dropped"]
    assert augmented.utilization.score > dropped.utilization.score
    assert augmented.utilization.score >= 55, (
        f"utilization {augmented.utilization.score} — effective augmentation should score well"
    )


def test_utilization_does_not_reward_low_ai_usage(analyses):
    """Utilization measures productive use, not abstinence.

    The excellent repository has the lowest assistance signals; it must not beat
    the augmented one *because* of that. Both should score well on their own
    merits.
    """
    excellent = analyses["excellent"]
    augmented = analyses["augmented"]
    assert augmented.utilization.score >= 55
    assert excellent.utilization.score >= 55


# -- Cross-cutting guarantees -------------------------------------------------

@pytest.mark.parametrize("name", list(BUILDERS))
def test_every_score_carries_evidence(analyses, name):
    result = analyses[name]
    for analyzer in (result.metrics, result.testing, result.documentation,
                     result.architecture, result.ownership):
        if analyzer.score is not None:
            assert analyzer.evidence, f"{name}/{analyzer.analyzer} produced a score with no evidence"


@pytest.mark.parametrize("name", list(BUILDERS))
def test_probabilistic_results_carry_confidence_and_limitations(analyses, name):
    result = analyses[name]
    assert 0.0 <= result.ai_usage.confidence <= 1.0
    assert result.ai_usage.limitations, "AI-usage analysis must state its limitations"
    assert result.similarity.limitations, "similarity analysis must state its limitations"
