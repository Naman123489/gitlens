"""Scoring engine, job parsing and matching tests."""

from __future__ import annotations

import pytest

from repolens_scoring import (
    DEFAULT_POLICY,
    AnalyzerFailure,
    EvaluationPolicy,
    PolicyError,
    RepositoryEvidence,
    VerificationSignals,
    engineering_dna,
    extract_skills,
    match_repository_to_job,
    parse_job_description,
    score_evaluation,
    validate_weights,
)
from repolens_shared import (
    AIUsageClassification,
    AnalyzerResult,
    OriginalityClassification,
    ScoreCategory,
    VerificationStatus,
)


def result(score: float | None, confidence: float = 0.9) -> AnalyzerResult:
    return AnalyzerResult(analyzer="test", version="1.0.0", score=score, confidence=confidence)


def all_categories(score: float = 80.0) -> dict[ScoreCategory, AnalyzerResult]:
    return {category: result(score) for category in ScoreCategory}


class TestJobParsing:
    @pytest.fixture
    def parsed(self):
        return parse_job_description(
            """We are looking for an AI/ML engineering intern.

Responsibilities:
- Build retrieval pipelines
- Ship inference services

Requirements:
- Strong Python
- PyTorch and Machine Learning
- RAG and vector databases
- FastAPI, SQL, Git

Nice to have:
- Docker and CI/CD
- React
""",
            title="AI/ML Engineering Intern",
        )

    def test_separates_required_from_preferred(self, parsed):
        required = {r.skill for r in parsed.required_skills()}
        preferred = {r.skill for r in parsed.preferred_skills()}
        assert {"python", "pytorch", "rag", "fastapi", "sql"} <= required
        assert {"docker", "ci_cd", "react"} <= preferred

    def test_importance_weights_sum_to_one(self, parsed):
        assert sum(r.importance for r in parsed.requirements) == pytest.approx(1.0, abs=1e-3)

    def test_detects_experience_level_and_domain(self, parsed):
        assert parsed.experience_level == "intern"
        assert parsed.domain == "ai_ml"

    def test_extracts_responsibilities(self, parsed):
        assert any("retrieval" in item.lower() for item in parsed.responsibilities)

    def test_adds_implied_skills_at_low_weight(self, parsed):
        implied = {r.skill: r for r in parsed.requirements if r.source == "implied"}
        assert implied
        explicit_max = max(r.importance for r in parsed.requirements if r.source == "explicit")
        assert all(r.importance < explicit_max for r in implied.values())

    def test_unrecognised_description_reports_a_note_rather_than_inventing_skills(self):
        parsed = parse_job_description("We need someone enthusiastic and collaborative.")
        assert parsed.requirements == [] or all(r.source == "implied" for r in parsed.requirements)
        assert parsed.notes

    def test_skill_extraction_resolves_overlaps_longest_first(self):
        found = extract_skills("machine learning engineer with ML experience")
        assert "machine_learning" in found


class TestJobMatching:
    @pytest.fixture
    def job(self):
        return parse_job_description(
            "Requirements:\n- Python\n- FastAPI\n- PostgreSQL\n- Testing\n\n"
            "Nice to have:\n- React\n",
            title="Backend Engineer",
        )

    def test_evidence_sources_drive_the_match(self, job):
        evidence = RepositoryEvidence(
            languages={"python": 50_000},
            dependencies={"fastapi", "uvicorn", "psycopg", "pytest"},
            imports={"fastapi"},
            paths=["app/api/routes.py", "tests/test_api.py"],
            signals={"testing": 0.9, "git": 1.0},
        )
        outcome, matches = match_repository_to_job(job, evidence)
        by_skill = {match.skill: match for match in matches}
        assert by_skill["python"].strength > 0.7
        assert by_skill["fastapi"].strength > 0.7
        assert by_skill["react"].strength == 0.0
        assert outcome.score > 50

    def test_missing_skills_are_named(self, job):
        outcome, _ = match_repository_to_job(job, RepositoryEvidence(languages={"java": 1000}))
        assert "React" not in outcome.metrics["missing_required_skills"]  # React is preferred
        assert outcome.metrics["missing_required_skills"]

    def test_every_matched_skill_cites_its_sources(self, job):
        _, matches = match_repository_to_job(
            job, RepositoryEvidence(dependencies={"fastapi"}, languages={"python": 100})
        )
        for match in matches:
            if match.matched:
                assert match.sources, f"{match.skill} matched with no cited source"

    def test_job_without_requirements_reports_unavailable_rather_than_zero(self):
        empty = parse_job_description("Be excellent.")
        empty.requirements = []
        outcome, matches = match_repository_to_job(empty, RepositoryEvidence())
        assert outcome.score is None
        assert outcome.partial
        assert matches == []

    def test_engineering_dna_covers_every_dimension(self):
        dna = engineering_dna(RepositoryEvidence(languages={"python": 100}, dependencies={"torch"}))
        assert set(dna) >= {"backend", "frontend", "ai_ml", "testing", "security"}
        assert dna["ai_ml"] > 0


class TestPolicies:
    def test_default_weights_sum_to_one(self):
        assert sum(DEFAULT_POLICY.weights.values()) == pytest.approx(1.0)

    def test_weights_are_normalised_not_required_to_sum_to_one(self):
        policy = EvaluationPolicy(
            name="Doubled",
            weights={category: weight * 2 for category, weight in DEFAULT_POLICY.weights.items()},
        )
        assert sum(policy.normalised_weights().values()) == pytest.approx(1.0)

    def test_rejects_negative_weights(self):
        with pytest.raises(PolicyError):
            validate_weights({ScoreCategory.TESTING: -0.5})

    def test_rejects_all_zero_weights(self):
        with pytest.raises(PolicyError):
            validate_weights({ScoreCategory.TESTING: 0.0})

    def test_round_trips_through_dict(self):
        restored = EvaluationPolicy.from_dict(DEFAULT_POLICY.to_dict())
        assert restored.weights == DEFAULT_POLICY.weights
        assert restored.version == DEFAULT_POLICY.version


class TestScoringEngine:
    def test_weighted_score_matches_the_policy(self):
        results = all_categories(80.0)
        results[ScoreCategory.TESTING] = result(40.0)
        evaluation = score_evaluation(results, VerificationSignals(ownership_confidence=80))
        # 80 everywhere except testing at 40, which carries 10% of the weight.
        assert evaluation.overall_score == pytest.approx(80 - 40 * 0.10, abs=0.01)

    def test_unavailable_category_is_renormalised_not_zeroed(self):
        results = all_categories(80.0)
        results[ScoreCategory.SECURITY] = None
        evaluation = score_evaluation(
            results,
            VerificationSignals(ownership_confidence=80),
            failures=[AnalyzerFailure("security", ScoreCategory.SECURITY, "scanner timed out", "now")],
        )
        # Zeroing security would drag the total below 80; renormalising keeps it.
        assert evaluation.overall_score == pytest.approx(80.0, abs=0.01)
        security = next(s for s in evaluation.scores if s.category == ScoreCategory.SECURITY)
        assert security.available is False
        assert "timed out" in (security.unavailable_reason or "")

    def test_confidence_falls_when_coverage_falls(self):
        full = score_evaluation(all_categories(80.0), VerificationSignals(ownership_confidence=80))
        partial_results = all_categories(80.0)
        for category in (ScoreCategory.SECURITY, ScoreCategory.TESTING, ScoreCategory.DOCUMENTATION):
            partial_results[category] = None
        partial = score_evaluation(partial_results, VerificationSignals(ownership_confidence=80))
        assert partial.confidence < full.confidence


class TestVerificationStatus:
    def test_clean_evaluation_is_clear(self):
        evaluation = score_evaluation(
            all_categories(80.0),
            VerificationSignals(
                ownership_confidence=88, ai_likelihood=30,
                ai_classification=AIUsageClassification.AI_ASSISTED,
                max_external_similarity=0.1,
                originality=OriginalityClassification.ORIGINAL,
            ),
        )
        assert evaluation.verification_status == VerificationStatus.CLEAR

    def test_thin_ownership_requires_verification(self):
        evaluation = score_evaluation(
            all_categories(80.0), VerificationSignals(ownership_confidence=30)
        )
        assert evaluation.verification_status == VerificationStatus.VERIFICATION_REQUIRED
        assert any("insufficient" in reason.lower() for reason in evaluation.verification_reasons)

    def test_incomplete_analysis_is_reported_as_incomplete(self):
        results = {category: None for category in ScoreCategory}
        results[ScoreCategory.TESTING] = result(70.0)
        evaluation = score_evaluation(results, VerificationSignals(ownership_confidence=80))
        assert evaluation.verification_status == VerificationStatus.ANALYSIS_INCOMPLETE

    def test_ai_signals_alone_never_require_verification_when_ownership_is_strong(self):
        """The central ethical rule: strong AI signals plus strong ownership is
        effective augmentation, not a problem to escalate."""
        evaluation = score_evaluation(
            all_categories(80.0),
            VerificationSignals(
                ownership_confidence=90, ai_likelihood=85,
                ai_classification=AIUsageClassification.AI_AUGMENTED,
                disclosure_provided=True,
            ),
        )
        assert evaluation.verification_status == VerificationStatus.CLEAR

    def test_no_status_is_ever_a_rejection(self):
        statuses = {str(status) for status in VerificationStatus}
        for forbidden in ("REJECT", "CHEATER", "FAKE", "AI_CHEATER", "AUTOMATIC_REJECT"):
            assert forbidden not in statuses

    def test_reasons_are_phrased_as_verification_not_accusation(self):
        evaluation = score_evaluation(
            all_categories(80.0),
            VerificationSignals(
                ownership_confidence=25, ai_likelihood=90,
                ai_classification=AIUsageClassification.AI_DOMINATED,
                max_external_similarity=0.9,
                originality=OriginalityClassification.STRONG_TUTORIAL_SIMILARITY,
            ),
        )
        text = " ".join(evaluation.verification_reasons).lower()
        for forbidden in ("reject", "cheat", "dishonest", "fraud", "lying"):
            assert forbidden not in text
        assert "misconduct" in text  # only as an explicit denial
        assert "not a finding of misconduct" in text

    def test_policy_thresholds_are_respected(self):
        strict = EvaluationPolicy(
            name="Strict",
            thresholds=type(DEFAULT_POLICY.thresholds)(ownership_review_below=95.0),
        )
        evaluation = score_evaluation(
            all_categories(80.0), VerificationSignals(ownership_confidence=90), policy=strict
        )
        assert evaluation.verification_status == VerificationStatus.REVIEW_RECOMMENDED


class TestReproducibility:
    def test_versions_are_recorded_on_every_evaluation(self):
        evaluation = score_evaluation(all_categories(80.0), VerificationSignals(ownership_confidence=80))
        assert evaluation.versions["analyzer_version"]
        assert evaluation.versions["scoring_engine"]
        assert evaluation.versions["policy_version"] == DEFAULT_POLICY.version

    def test_scoring_is_deterministic(self):
        signals = VerificationSignals(ownership_confidence=72, ai_likelihood=44)
        first = score_evaluation(all_categories(77.5), signals).to_dict()
        second = score_evaluation(all_categories(77.5), signals).to_dict()
        assert first == second
