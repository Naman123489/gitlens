"""Evaluation assembly.

Combines a completed repository analysis with a job and a policy version to
produce a persisted, explainable :class:`Evaluation`.

The scoring itself lives in ``packages/scoring``; this module's job is to gather
the inputs, persist the outputs and leave an audit trail.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from repolens_scoring import (
    AnalyzerFailure,
    EvaluationPolicy,
    ParsedJob,
    RepositoryEvidence,
    VerificationSignals,
    engineering_dna,
    match_repository_to_job,
    score_evaluation,
)
from repolens_scoring.jd_parser import ParsedRequirement
from repolens_shared import (
    AIUsageClassification,
    AnalyzerResult,
    OriginalityClassification,
    RunVersions,
    ScoreCategory,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import (
    Candidate,
    Evaluation,
    EvaluationScore,
    EvidenceRecord,
    Job,
    Recommendation as RecommendationRow,
    Repository,
    RepositoryAnalysis,
    RepositoryDependency,
    RepositoryFile,
    User,
)
from app.services import narrative, recommendations, resume
from app.services.evidence_io import results_from_analysis
from app.services.pipeline import ANALYZER_CATEGORY

logger = get_logger("repolens.evaluation")


def build_repository_evidence(
    db: Session, repository: Repository, analysis: RepositoryAnalysis
) -> RepositoryEvidence:
    """Gather the observable facts the job matcher is allowed to use."""
    files = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id).all()
    dependencies = (
        db.query(RepositoryDependency)
        .filter(RepositoryDependency.repository_id == repository.id)
        .all()
    )
    results = analysis.results or {}

    languages: dict[str, int] = {}
    for file in files:
        if file.language and file.category in ("CANDIDATE_CODE", "TEST_CODE"):
            languages[file.language] = languages.get(file.language, 0) + max(1, file.size_bytes)
    if not languages and repository.languages:
        languages = dict(repository.languages)

    imports: set[str] = set()
    for dependency in dependencies:
        imports.add(dependency.name.split("/")[-1].replace("-", "_"))

    testing = (results.get("testing") or {}).get("metrics") or {}
    git_history = (results.get("git_history") or {}).get("metrics") or {}
    architecture = (results.get("architecture") or {}).get("metrics") or {}
    security = (results.get("security") or {}).get("metrics") or {}
    paths = [f.path for f in files]

    signals: dict[str, float] = {}
    if git_history.get("available"):
        signals["git"] = 1.0
    if testing.get("test_cases"):
        signals["testing"] = min(1.0, 0.5 + float(testing["test_cases"]) / 60.0)
    if testing.get("ci_runs_tests"):
        signals["ci_cd"] = 1.0
    if any(p.rsplit("/", 1)[-1].lower().startswith("dockerfile") or "docker-compose" in p.lower()
           for p in paths):
        signals["docker"] = 1.0
    if "api_layer" in (architecture.get("layers_detected") or []):
        signals["rest_api"] = 0.8
    if any(f.get("category") == "auth" for f in (security.get("findings") or [])):
        signals["security"] = 0.5
    if any(p.endswith(".ipynb") or "/notebooks/" in p or p.startswith("notebooks/") for p in paths):
        signals["research"] = 0.8
    if any(p.upper().startswith("CONTRIBUTING") for p in paths):
        signals["open_source"] = 0.7

    return RepositoryEvidence(
        languages=languages,
        dependencies={d.name for d in dependencies},
        imports=imports,
        paths=paths,
        topics=list(repository.topics or []),
        readme=repository.readme or "",
        description=repository.description or "",
        signals=signals,
    )


def parsed_job_from_record(job: Job) -> ParsedJob:
    parsed = ParsedJob(
        responsibilities=list(job.responsibilities or []),
        experience_level=job.experience_level,
        min_years_experience=job.min_years_experience,
        domain=job.domain,
        notes=list(job.parse_notes or []),
    )
    parsed.requirements = [
        ParsedRequirement(
            skill=r.skill, label=r.label, dimension=r.dimension, required=r.required,
            importance=r.importance, matched_terms=list(r.matched_terms or []), source=r.source,
        )
        for r in job.requirements
    ]
    return parsed


def create_evaluation(
    db: Session,
    repository: Repository,
    analysis: RepositoryAnalysis,
    policy: EvaluationPolicy,
    policy_id: str | None = None,
    job: Job | None = None,
    candidate: Candidate | None = None,
    user: User | None = None,
    organization_id: str | None = None,
    verification_score: float | None = None,
    include_narrative: bool = True,
) -> Evaluation:
    """Score one repository against one job under one policy version."""
    settings = get_settings()
    results: dict[str, AnalyzerResult] = results_from_analysis(analysis.results)
    evidence_repo = build_repository_evidence(db, repository, analysis)

    by_category: dict[ScoreCategory, AnalyzerResult | None] = {}
    for analyzer_name, category in ANALYZER_CATEGORY.items():
        result = results.get(analyzer_name)
        if result is None:
            continue
        existing = by_category.get(category)
        if existing is None or (existing.score is None and result.score is not None):
            by_category[category] = result
        elif existing.score is not None and result.score is not None:
            # Two analyzers feed architecture (structure + dependencies): combine
            # them rather than letting the later one silently win.
            by_category[category] = _merge(existing, result, category)

    skill_matches: list[dict[str, Any]] = []
    missing_required: list[str] = []
    if job is not None:
        parsed = parsed_job_from_record(job)
        match_result, matches = match_repository_to_job(parsed, evidence_repo)
        by_category[ScoreCategory.JOB_RELEVANCE] = match_result
        skill_matches = [m.to_dict() for m in matches]
        missing_required = list(match_result.metrics.get("missing_required_skills") or [])

    similarity = results.get("similarity")
    ai_usage = results.get("ai_usage")
    ownership = results.get("ownership")
    utilization = results.get("ai_utilization")

    resume_consistency = None
    resume_gaps = 0
    if candidate is not None and candidate.resume_parsed:
        parsed_resume = resume.ParsedResume(**{
            k: v for k, v in candidate.resume_parsed.items()
            if k in resume.ParsedResume.__slots__
        })
        strengths = {m["skill"]: float(m["strength"]) for m in skill_matches}
        if not strengths:
            strengths = _all_skill_strengths(evidence_repo)
        resume_consistency = resume.compare_resume_to_evidence(parsed_resume, strengths)
        resume_gaps = int(resume_consistency["verification_recommended"])

    signals = VerificationSignals(
        ownership_confidence=ownership.score if ownership else None,
        ai_likelihood=float(ai_usage.metrics.get("estimated_ai_assistance")) if ai_usage else None,
        ai_classification=(
            AIUsageClassification(ai_usage.metrics["classification"]) if ai_usage else None
        ),
        max_external_similarity=(
            similarity.metrics.get("max_external_similarity") if similarity else None
        ),
        originality=(
            OriginalityClassification(similarity.metrics["originality"]) if similarity else None
        ),
        resume_gaps=resume_gaps,
        analysis_complete=not analysis.is_partial or bool(analysis.category_scores),
        disclosure_provided=bool(candidate and candidate.ai_disclosure),
    )

    failures = [
        AnalyzerFailure(
            analyzer=f.get("analyzer", ""),
            category=ScoreCategory(f["category"]) if f.get("category") else None,
            reason=f.get("reason", ""), occurred_at=f.get("occurred_at", ""),
        )
        for f in analysis.failures or []
    ]

    scored = score_evaluation(
        results=by_category, signals=signals, policy=policy, failures=failures,
        versions=RunVersions(
            analyzer_version=analysis.analyzer_version,
            policy_version=policy.version,
            llm_model=settings.llm_model if settings.llm_configured else None,
        ),
    )

    evaluation = Evaluation(
        organization_id=organization_id,
        candidate_id=candidate.id if candidate else None,
        user_id=user.id if user else repository.owner_user_id,
        job_id=job.id if job else None,
        repository_id=repository.id,
        analysis_id=analysis.id,
        policy_id=policy_id,
        overall_score=scored.overall_score,
        confidence=scored.confidence,
        job_match=(
            by_category[ScoreCategory.JOB_RELEVANCE].score
            if ScoreCategory.JOB_RELEVANCE in by_category else None
        ),
        ownership_confidence=ownership.score if ownership else None,
        ai_likelihood=signals.ai_likelihood,
        ai_utilization=utilization.score if utilization else None,
        ai_classification=str(signals.ai_classification) if signals.ai_classification else None,
        originality=str(signals.originality) if signals.originality else None,
        verification_status=str(scored.verification_status),
        verification_reasons=scored.verification_reasons,
        limitations=scored.limitations,
        failures=scored.failures,
        skill_matches=skill_matches,
        engineering_dna=engineering_dna(evidence_repo),
        resume_consistency=resume_consistency,
        versions=scored.versions,
        is_demo=repository.is_demo,
    )
    db.add(evaluation)
    db.flush()

    weights = {str(k): v for k, v in policy.weights.items()}
    analyzer_metrics = {name: result.metrics for name, result in results.items()}
    for category_score in scored.scores:
        source = by_category.get(category_score.category)
        db.add(EvaluationScore(
            evaluation_id=evaluation.id,
            category=str(category_score.category),
            score=category_score.score if category_score.available else None,
            confidence=category_score.confidence,
            weight=weights.get(str(category_score.category), 0.0),
            available=category_score.available,
            unavailable_reason=category_score.unavailable_reason,
            evidence_ids=list(category_score.evidence_ids),
            sub_scores=(source.metrics.get("sub_scores") or {}) if source else {},
        ))

    seen: set[str] = set()
    for item in scored.evidence:
        evidence_id = item.evidence_id()
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        payload = item.to_dict()
        db.add(EvidenceRecord(
            evaluation_id=evaluation.id, evidence_id=evidence_id,
            category=payload["category"], claim=payload["claim"], severity=payload["severity"],
            confidence=payload["confidence"], supports=payload["supports"],
            tags=payload["tags"], details=payload["evidence"],
            analyzer=_analyzer_for_category(payload["category"]),
        ))

    category_values = {
        str(s.category): s.score for s in scored.scores if s.available
    }
    evidence_payload = [{"id": e.evidence_id(), **e.to_dict()} for e in scored.evidence]
    for recommendation in recommendations.generate(
        analyzer_metrics=analyzer_metrics, category_scores=category_values,
        weights=weights, evidence=evidence_payload, missing_job_skills=missing_required,
    )[:12]:
        db.add(RecommendationRow(
            evaluation_id=evaluation.id, repository_id=repository.id,
            user_id=evaluation.user_id, category=recommendation.category,
            title=recommendation.title, detail=recommendation.detail,
            impact=recommendation.impact, effort=recommendation.effort,
            evidence_ids=recommendation.evidence_ids, expected_gain=recommendation.expected_gain,
            generated_by="deterministic",
        ))

    if include_narrative:
        evaluation.narrative = narrative.evaluation_summary({
            "overall_score": scored.overall_score,
            "verification_status": str(scored.verification_status),
            "verification_reasons": scored.verification_reasons,
            "scores": [s.to_dict() for s in scored.scores],
            "evidence": evidence_payload,
            "ai_analysis": ai_usage.metrics if ai_usage else None,
            "limitations": scored.limitations,
        })
    db.add(evaluation)
    db.flush()
    return evaluation


def _merge(left: AnalyzerResult, right: AnalyzerResult, category: ScoreCategory) -> AnalyzerResult:
    """Average two analyzers that feed the same category, keeping both evidence sets."""
    merged = AnalyzerResult(
        analyzer=f"{left.analyzer}+{right.analyzer}",
        version=left.version,
        metrics={left.analyzer: left.metrics, right.analyzer: right.metrics},
        evidence=[*left.evidence, *right.evidence],
        limitations=[*left.limitations, *right.limitations],
        score=round(((left.score or 0.0) * 0.65 + (right.score or 0.0) * 0.35), 2),
        confidence=min(left.confidence, right.confidence),
        partial=left.partial or right.partial,
    )
    return merged


def _analyzer_for_category(category: str) -> str:
    for analyzer, mapped in ANALYZER_CATEGORY.items():
        if str(mapped) == category:
            return analyzer
    return ""


def _all_skill_strengths(evidence: RepositoryEvidence) -> dict[str, float]:
    """Evidence strength for every skill in the taxonomy, for résumé comparison
    when no job has been selected."""
    from repolens_scoring.matching import _skill_strength
    from repolens_scoring.taxonomy import SKILLS_BY_KEY

    return {
        key: _skill_strength(skill, evidence)[0] for key, skill in SKILLS_BY_KEY.items()
    }
