"""The student portal: engineering profile, readiness and improvement plan."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from repolens_scoring import SKILLS_BY_KEY, parse_job_description
from repolens_scoring.matching import match_repository_to_job

from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.models import (
    Candidate,
    Evaluation,
    EvaluationScore,
    Job,
    Recommendation,
    Repository,
    RepositoryAnalysis,
    User,
)
from app.services.evaluation_service import build_repository_evidence, parsed_job_from_record

router = APIRouter(prefix="/me", tags=["student"])

#: Role archetypes the readiness panel reports against, as job descriptions the
#: existing parser understands. Kept as data so they are auditable.
#: The parser reads "Requirements:" and "Nice to have:" as section headings, so
#: they must sit on their own lines exactly as a real description would.
ROLE_TEMPLATES: dict[str, str] = {
    "AI Engineer": """Requirements:
- Python
- PyTorch and machine learning
- LLM integration and RAG
- Vector databases
- FastAPI
- Testing
- Git

Nice to have:
- Docker
- CI/CD
""",
    "Backend Engineer": """Requirements:
- Python
- REST API development
- SQL and PostgreSQL
- ORM and data modelling
- Testing
- Git
- Docker

Nice to have:
- Redis
- Message queues
- CI/CD
- Security engineering
""",
    "Full Stack Engineer": """Requirements:
- TypeScript
- React
- REST API development
- SQL
- Testing
- Git

Nice to have:
- Next.js
- Tailwind CSS
- Docker
- CI/CD
""",
    "Data Scientist": """Requirements:
- Python
- Data science and pandas
- Machine learning
- SQL
- Research and experimentation

Nice to have:
- PyTorch
- Data engineering
- Data visualisation
""",
    "DevOps Engineer": """Requirements:
- Docker
- Kubernetes
- CI/CD
- Cloud platforms
- Infrastructure as code
- Observability
- Shell scripting
- Git

Nice to have:
- Message queues
- Security engineering
""",
}


def _dedupe_recommendations(rows: list[Recommendation]) -> list[Recommendation]:
    """One row per (repository, title), best expected gain first."""
    best: dict[tuple[str | None, str], Recommendation] = {}
    for row in rows:
        key = (row.repository_id, row.title)
        current = best.get(key)
        if current is None or (row.expected_gain or 0) > (current.expected_gain or 0):
            best[key] = row
    return sorted(best.values(), key=lambda r: -(r.expected_gain or 0))


def _own_repositories(db: Session, user: User) -> list[Repository]:
    return db.query(Repository).filter(Repository.owner_user_id == user.id).all()


def _latest_evaluations(db: Session, user: User) -> list[Evaluation]:
    candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    from sqlalchemy import or_

    conditions = [Evaluation.user_id == user.id]
    if candidate is not None:
        conditions.append(Evaluation.candidate_id == candidate.id)
    return (
        db.query(Evaluation)
        .filter(or_(*conditions))
        .order_by(Evaluation.created_at.desc())
        .limit(100).all()
    )


@router.get("/dashboard", response_model=dict)
def dashboard(user: CurrentUser, db: DbSession) -> dict:
    """Everything the student home page needs, in one call."""
    repositories = _own_repositories(db, user)
    evaluations = _latest_evaluations(db, user)
    analysed = [r for r in repositories if r.analysis_status == "COMPLETED"]

    latest_by_repository: dict[str, Evaluation] = {}
    for evaluation in evaluations:
        latest_by_repository.setdefault(evaluation.repository_id, evaluation)

    analyses = {
        a.repository_id: a
        for a in db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id.in_([r.id for r in repositories] or ["-"]))
        .order_by(RepositoryAnalysis.created_at.desc()).all()
    }

    scores = [
        a.repository_score for a in analyses.values() if a.repository_score is not None
    ]
    # The profile score weights each repository's own score by how much evidence
    # it carries, so a one-file experiment cannot drag down a substantial project.
    weighted: list[tuple[float, float]] = []
    for repository in analysed:
        analysis = analyses.get(repository.id)
        if analysis is None or analysis.repository_score is None:
            continue
        files = int(((analysis.stats or {}).get("files") or {}).get("analysed", 1))
        weight = min(3.0, 0.5 + files / 60.0)
        weighted.append((analysis.repository_score, weight))
    engineering_score = (
        round(sum(s * w for s, w in weighted) / sum(w for _, w in weighted), 1)
        if weighted else None
    )

    dna: dict[str, float] = {}
    for evaluation in latest_by_repository.values():
        for key, value in (evaluation.engineering_dna or {}).items():
            dna[key] = max(dna.get(key, 0.0), float(value))

    # Recommendations are generated per evaluation, so the same advice recurs
    # across re-runs and across repositories. Collapse by title, keeping the
    # instance with the largest expected gain.
    recommendations = _dedupe_recommendations(
        db.query(Recommendation)
        .filter(Recommendation.user_id == user.id)
        .order_by(Recommendation.expected_gain.desc().nullslast())
        .limit(60).all()
    )[:8]

    strengths: list[dict] = []
    weaknesses: list[dict] = []
    for evaluation in list(latest_by_repository.values())[:6]:
        for score in db.query(EvaluationScore).filter(
            EvaluationScore.evaluation_id == evaluation.id, EvaluationScore.available.is_(True)
        ).all():
            bucket = strengths if (score.score or 0) >= 75 else (
                weaknesses if (score.score or 0) < 55 else None
            )
            if bucket is not None:
                bucket.append({
                    "category": score.category, "score": score.score,
                    "repository_id": evaluation.repository_id,
                })

    return {
        "engineering_score": engineering_score,
        "engineering_score_basis": {
            "repositories_analysed": len(weighted),
            "method": "Repository scores weighted by the amount of analysed code in each.",
        },
        "repositories": {
            "total": len(repositories),
            "analysed": len(analysed),
            "pending": len([r for r in repositories if r.analysis_status in ("QUEUED", "RUNNING")]),
        },
        "engineering_dna": dna,
        "strengths": sorted(strengths, key=lambda s: -(s["score"] or 0))[:6],
        "weaknesses": sorted(weaknesses, key=lambda s: (s["score"] or 0))[:6],
        "recommendations": [
            {
                "category": r.category, "title": r.title, "detail": r.detail, "impact": r.impact,
                "effort": r.effort, "expected_gain": r.expected_gain,
            }
            for r in recommendations
        ],
        "repository_summaries": [
            {
                "id": r.id, "full_name": r.full_name, "name": r.name,
                "primary_language": r.primary_language, "analysis_status": r.analysis_status,
                "score": analyses[r.id].repository_score if r.id in analyses else None,
                "ownership_confidence": (
                    analyses[r.id].ownership_confidence if r.id in analyses else None
                ),
                "ai_classification": analyses[r.id].ai_classification if r.id in analyses else None,
                "evaluation_id": (
                    latest_by_repository[r.id].id if r.id in latest_by_repository else None
                ),
                "last_analyzed_at": r.last_analyzed_at,
            }
            for r in repositories
        ],
        "empty_state": None if repositories else {
            "title": "No repositories analysed yet",
            "detail": "Connect GitHub to begin your engineering profile.",
        },
    }


@router.get("/readiness", response_model=dict)
def readiness(user: CurrentUser, db: DbSession, job_id: str | None = None) -> dict:
    """Job-readiness across role archetypes, or against one specific job."""
    repositories = _own_repositories(db, user)
    analyses = {}
    for repository in repositories:
        analysis = (
            db.query(RepositoryAnalysis)
            .filter(RepositoryAnalysis.repository_id == repository.id)
            .order_by(RepositoryAnalysis.created_at.desc())
            .first()
        )
        if analysis is not None:
            analyses[repository.id] = analysis

    if not analyses:
        return {
            "roles": [], "repositories": 0,
            "empty_state": {
                "title": "Nothing to match yet",
                "detail": "Analyse at least one repository to see how it maps onto real roles.",
            },
        }

    evidence_by_repository = {
        repository_id: build_repository_evidence(db, db.get(Repository, repository_id), analysis)
        for repository_id, analysis in analyses.items()
    }

    targets: list[tuple[str, object]] = []
    if job_id:
        job = db.get(Job, job_id)
        if job is None:
            raise NotFoundError("Job not found.")
        targets.append((job.title, parsed_job_from_record(job)))
    else:
        for role, description in ROLE_TEMPLATES.items():
            targets.append((role, parse_job_description(description, title=role)))

    roles: list[dict] = []
    for label, parsed in targets:
        per_repository: list[dict] = []
        best_strengths: dict[str, float] = {}
        for repository_id, evidence in evidence_by_repository.items():
            result, matches = match_repository_to_job(parsed, evidence)
            repository = db.get(Repository, repository_id)
            per_repository.append({
                "repository_id": repository_id,
                "full_name": repository.full_name if repository else repository_id,
                "match": result.score,
                "missing": result.metrics.get("missing_required_skills", []),
            })
            for match in matches:
                best_strengths[match.skill] = max(best_strengths.get(match.skill, 0.0), match.strength)

        # Readiness across a portfolio is the best evidence found anywhere, not
        # the average: a candidate's strongest project is what a role cares about.
        total_weight = sum(r.importance for r in parsed.requirements) or 1.0
        readiness_score = 100.0 * sum(
            best_strengths.get(r.skill, 0.0) * r.importance for r in parsed.requirements
        ) / total_weight
        missing = [
            SKILLS_BY_KEY[r.skill].label
            for r in parsed.requirements
            if r.required and best_strengths.get(r.skill, 0.0) < 0.2 and r.skill in SKILLS_BY_KEY
        ]
        roles.append({
            "role": label,
            "readiness": round(readiness_score, 1),
            "missing_required": missing,
            "evidenced": [
                {"skill": key, "label": SKILLS_BY_KEY[key].label, "strength": round(value, 3)}
                for key, value in sorted(best_strengths.items(), key=lambda kv: -kv[1])[:8]
                if value >= 0.2 and key in SKILLS_BY_KEY
            ],
            "per_repository": sorted(per_repository, key=lambda r: -(r["match"] or 0))[:5],
        })

    return {
        "roles": sorted(roles, key=lambda r: -r["readiness"]),
        "repositories": len(analyses),
        "note": "Readiness uses the strongest evidence found across your repositories for each "
                "required skill.",
    }


@router.get("/recommendations", response_model=list[dict])
def my_recommendations(
    user: CurrentUser, db: DbSession, limit: int = Query(default=20, ge=1, le=50)
) -> list[dict]:
    rows = _dedupe_recommendations(
        db.query(Recommendation)
        .filter(Recommendation.user_id == user.id)
        .order_by(Recommendation.expected_gain.desc().nullslast())
        .limit(limit * 6).all()
    )[:limit]
    return [
        {
            "id": r.id, "category": r.category, "title": r.title, "detail": r.detail,
            "impact": r.impact, "effort": r.effort, "expected_gain": r.expected_gain,
            "repository_id": r.repository_id, "evaluation_id": r.evaluation_id,
        }
        for r in rows
    ]
