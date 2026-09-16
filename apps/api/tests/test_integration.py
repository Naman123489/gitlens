"""End-to-end integration: ingestion → analysis → scoring → evidence → report.

Runs the real pipeline against a synthetic git repository built on disk, with no
network access and no mocking of the analysis engine.
"""

from __future__ import annotations

import pytest

from repolens_scoring import DEFAULT_POLICY
from repolens_shared import ScoreCategory

from tests.conftest import auth
from tests.fixtures import build_excellent_repository, local_fetcher


@pytest.fixture
def analysed_repository(db, tmp_path):
    """Import a local repository and run the full pipeline over it."""
    from app.models import Candidate, Repository, User
    from app.services.pipeline import run_pipeline

    path = build_excellent_repository(tmp_path)

    user = User(email="pipeline@example.com", full_name="Pipeline User", role="STUDENT")
    db.add(user)
    db.flush()
    candidate = Candidate(user_id=user.id, full_name="Pipeline User", email=user.email)
    db.add(candidate)
    db.flush()

    repository = Repository(
        owner_user_id=user.id, candidate_id=candidate.id, name="ledger",
        full_name="pipeline/ledger", clone_url=f"file://{path}", default_branch="main",
    )
    db.add(repository)
    db.flush()

    fetcher = local_fetcher(path)
    outcome = run_pipeline(db, repository, corpus_enabled=False, fetcher=fetcher)
    return {
        "user": user, "candidate": candidate, "repository": repository,
        "outcome": outcome, "fetcher": local_fetcher(path),
    }


class TestPipeline:
    def test_pipeline_completes_with_no_analyzer_failures(self, analysed_repository):
        outcome = analysed_repository["outcome"]
        assert outcome.failures == [], f"analyzers failed: {[f.analyzer for f in outcome.failures]}"
        assert outcome.analysis.repository_score is not None

    def test_pipeline_classifies_files(self, analysed_repository):
        categories = analysed_repository["outcome"].stats["files"]["by_category"]
        assert categories.get("CANDIDATE_CODE", 0) >= 2
        assert categories.get("TEST_CODE", 0) >= 1
        assert categories.get("DOCUMENTATION", 0) >= 1

    def test_pipeline_persists_its_artefacts(self, analysed_repository, db):
        from app.models import CodeChunk, RepositoryCommit, RepositoryDependency, RepositoryFile

        repository_id = analysed_repository["repository"].id
        assert db.query(RepositoryFile).filter(
            RepositoryFile.repository_id == repository_id
        ).count() > 0
        assert db.query(RepositoryCommit).filter(
            RepositoryCommit.repository_id == repository_id
        ).count() >= 5
        assert db.query(RepositoryDependency).filter(
            RepositoryDependency.repository_id == repository_id
        ).count() > 0
        assert db.query(CodeChunk).filter(CodeChunk.repository_id == repository_id).count() > 0

    def test_analysis_records_evidence_and_limitations(self, analysed_repository):
        analysis = analysed_repository["outcome"].analysis
        assert len(analysis.evidence) >= 10
        assert analysis.limitations, "an analysis must always state its limitations"
        assert all("claim" in item for item in analysis.evidence)

    def test_reanalysis_detects_unchanged_files(self, analysed_repository, db):
        """Incremental analysis: a second run finds the content hashes unchanged."""
        from app.services.pipeline import run_pipeline

        second = run_pipeline(
            db, analysed_repository["repository"], corpus_enabled=False,
            fetcher=analysed_repository["fetcher"],
        )
        assert second.stats["ast"]["unchanged_since_last_run"] > 0
        assert second.analysis.id != analysed_repository["outcome"].analysis.id


class TestEvaluationFlow:
    def test_evaluation_produces_traceable_scores(self, analysed_repository, db):
        from app.models import EvaluationScore, EvidenceRecord
        from app.services.evaluation_service import create_evaluation

        evaluation = create_evaluation(
            db=db,
            repository=analysed_repository["repository"],
            analysis=analysed_repository["outcome"].analysis,
            policy=DEFAULT_POLICY,
            candidate=analysed_repository["candidate"],
            user=analysed_repository["user"],
        )

        assert evaluation.overall_score is not None
        scores = db.query(EvaluationScore).filter(
            EvaluationScore.evaluation_id == evaluation.id
        ).all()
        assert len(scores) == len(list(ScoreCategory))

        evidence_ids = {
            row.evidence_id for row in
            db.query(EvidenceRecord).filter(EvidenceRecord.evaluation_id == evaluation.id).all()
        }
        assert evidence_ids

        # Every evidence id referenced by a score must exist as an evidence row.
        for score in scores:
            for evidence_id in score.evidence_ids:
                assert evidence_id in evidence_ids, (
                    f"{score.category} references evidence {evidence_id} that was not persisted"
                )

    def test_evaluation_against_a_job_matches_real_skills(self, analysed_repository, db):
        from app.models import Job, JobRequirement
        from app.services.evaluation_service import create_evaluation
        from repolens_scoring import parse_job_description

        job = Job(
            title="Backend Engineer",
            description="Requirements:\n- Python\n- Testing\n- Git\n\nNice to have:\n- Docker\n",
        )
        db.add(job)
        db.flush()
        parsed = parse_job_description(job.description, title=job.title)
        for requirement in parsed.requirements:
            db.add(JobRequirement(
                job_id=job.id, skill=requirement.skill, label=requirement.label,
                dimension=requirement.dimension, required=requirement.required,
                importance=requirement.importance, source=requirement.source,
                matched_terms=requirement.matched_terms,
            ))
        db.flush()

        evaluation = create_evaluation(
            db=db,
            repository=analysed_repository["repository"],
            analysis=analysed_repository["outcome"].analysis,
            policy=DEFAULT_POLICY,
            job=job,
            candidate=analysed_repository["candidate"],
            user=analysed_repository["user"],
        )

        assert evaluation.job_match is not None
        matches = {match["skill"]: match for match in evaluation.skill_matches}
        assert matches["python"]["strength"] > 0.5
        assert matches["testing"]["strength"] > 0.3
        assert matches["python"]["sources"], "a matched skill must cite its evidence"

    def test_resume_consistency_is_computed_when_a_resume_exists(self, analysed_repository, db):
        from app.services.evaluation_service import create_evaluation
        from app.services.resume import parse_resume

        candidate = analysed_repository["candidate"]
        candidate.resume_parsed = parse_resume(
            "Skills:\n- Python (Advanced)\n- Kubernetes (Expert)\n"
        ).to_dict()
        db.add(candidate)
        db.flush()

        evaluation = create_evaluation(
            db=db,
            repository=analysed_repository["repository"],
            analysis=analysed_repository["outcome"].analysis,
            policy=DEFAULT_POLICY,
            candidate=candidate,
            user=analysed_repository["user"],
        )

        consistency = evaluation.resume_consistency
        assert consistency is not None
        by_skill = {item["skill"]: item for item in consistency["items"]}
        # Kubernetes is claimed at expert level and appears nowhere in the code.
        assert by_skill["kubernetes"]["status"] == "verification_recommended"
        # The wording must stay non-accusatory.
        assert "prompt to ask" in by_skill["kubernetes"]["detail"]
        assert "not evidence of absence" in consistency["limitation"].lower() or \
               "would not appear here" in by_skill["kubernetes"]["detail"]


class TestInterviewGeneration:
    def test_questions_are_anchored_to_real_repository_artefacts(self, analysed_repository):
        from app.services.interview import generate_questions

        analysis = analysed_repository["outcome"].analysis
        questions = generate_questions(analysis.results, "pipeline/ledger")

        assert len(questions) >= 5
        assert all(question.rationale for question in questions)
        # At least one question must cite a real file from this repository.
        anchored = [question for question in questions if question.anchors]
        assert anchored, "no question was anchored to a repository artefact"
        files = {anchor["file"] for question in anchored for anchor in question.anchors}
        assert any(name.endswith(".py") for name in files)
        assert all(question.generated_by != "fallback" for question in questions[:3])

    def test_answer_assessment_discriminates(self, analysed_repository):
        from app.services.interview import assess_answer, generate_questions

        analysis = analysed_repository["outcome"].analysis
        question = generate_questions(analysis.results, "pipeline/ledger")[0].to_dict()
        facts = {
            "test_cases": 5, "ci_runs_tests": True, "languages": ["python"],
            "files": ["services/posting.py"], "symbols": ["post", "validate_amount"],
        }

        weak = assess_answer(question, "It does stuff.", facts)
        strong = assess_answer(
            question,
            "`post` in `services/posting.py` validates the amount first, because a zero or "
            "negative posting would silently unbalance the ledger. It then returns the debit and "
            "credit entries as a pair so the caller cannot write one without the other. I tested "
            "the failure paths in tests/test_posting.py rather than only the happy path.",
            facts,
        )
        assert strong["score"] > weak["score"] + 20
        assert strong["dimensions"]["specificity"]["score"] > weak["dimensions"]["specificity"]["score"]
        assert "limitation" in strong


class TestReport:
    def test_markdown_report_contains_the_required_sections(self, analysed_repository, db):
        from app.api.v1.reports import _build, _render_markdown
        from app.services.evaluation_service import create_evaluation

        evaluation = create_evaluation(
            db=db,
            repository=analysed_repository["repository"],
            analysis=analysed_repository["outcome"].analysis,
            policy=DEFAULT_POLICY,
            candidate=analysed_repository["candidate"],
            user=analysed_repository["user"],
        )
        markdown = _render_markdown(_build(db, evaluation, include_private=True))

        for heading in (
            "## Summary", "## Scores", "## Technical strengths", "## Weaknesses",
            "## AI usage analysis", "## Ownership analysis", "## Similarity analysis",
            "## Security", "## Limitations", "## Reproducibility",
        ):
            assert heading in markdown, f"report is missing {heading}"

        assert "decision support, not a decision" in markdown
        for forbidden in ("reject", "cheat", "plagiari"):
            assert forbidden not in markdown.lower()
