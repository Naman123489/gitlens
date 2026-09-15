"""Repository listing, import, analysis and analysis artefacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from repolens_github import (
    GitHubClient,
    GitHubError,
    RateLimitedError,
    probe_public_repository,
)

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, user_organization_ids
from app.core.errors import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.security import decrypt_secret
from app.models import (
    AnalysisJob,
    Candidate,
    GitHubAccount,
    Repository,
    RepositoryAnalysis,
    RepositoryCommit,
    RepositoryFile,
    SecurityFinding,
    SimilarityResult,
    User,
)
from app.schemas.common import Message, Page
from app.schemas.repository import (
    AnalysisDetailOut,
    AnalysisJobOut,
    AnalysisOut,
    AnalyzeRequest,
    CommitOut,
    GitHubRepositoryOut,
    ImportRepositoryRequest,
    RepositoryOut,
    SecurityFindingOut,
    SimilarityOut,
)
from app.services import audit
from app.services.queue import backend_status, enqueue
from app.services.ratelimit_dep import analysis_rate_limit
from app.workers.analysis_worker import initial_stages, run_analysis_job

router = APIRouter(tags=["repositories"])


def _visible_repository(db: Session, user: User, repository_id: str) -> Repository:
    """Fetch a repository the caller is allowed to see.

    Visibility: the owner, an administrator, or an interviewer in the
    organization that the linked candidate belongs to.
    """
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise NotFoundError("Repository not found.")
    if user.role == "ADMIN" or repository.owner_user_id == user.id:
        return repository
    if repository.candidate_id:
        candidate = db.get(Candidate, repository.candidate_id)
        if candidate and candidate.organization_id in user_organization_ids(db, user):
            return repository
    raise NotFoundError("Repository not found.")


@router.get("/github/repositories", response_model=list[GitHubRepositoryOut])
async def list_github_repositories(
    user: CurrentUser, db: DbSession,
    account_id: str | None = None,
    include_forks: bool = False,
    include_archived: bool = False,
) -> list[GitHubRepositoryOut]:
    """List repositories on GitHub for the caller's connected account."""
    query = db.query(GitHubAccount).filter(GitHubAccount.user_id == user.id)
    if account_id:
        query = query.filter(GitHubAccount.id == account_id)
    account = query.order_by(GitHubAccount.created_at.desc()).first()
    if account is None:
        raise ValidationError(
            "No GitHub account is connected. Connect GitHub to list your repositories."
        )
    token = decrypt_secret(account.access_token_encrypted)
    if not token:
        raise ValidationError(
            "The stored GitHub credential could not be read. Reconnect your GitHub account."
        )

    try:
        async with GitHubClient(token) as client:
            repositories = await client.list_repositories()
    except RateLimitedError as exc:
        raise ServiceUnavailableError(str(exc)) from exc
    except GitHubError as exc:
        raise ServiceUnavailableError(f"GitHub request failed: {exc}") from exc

    imported = {
        row.full_name: row.id
        for row in db.query(Repository).filter(Repository.owner_user_id == user.id).all()
    }
    return [
        GitHubRepositoryOut(
            external_id=str(repo.id), name=repo.name, full_name=repo.full_name,
            description=repo.description, html_url=repo.html_url, clone_url=repo.clone_url,
            default_branch=repo.default_branch, language=repo.language,
            stars=repo.stargazers_count, forks=repo.forks_count, size_kb=repo.size_kb,
            private=repo.private, fork=repo.fork, archived=repo.archived, topics=repo.topics,
            pushed_at=repo.pushed_at, imported=repo.full_name in imported,
            repository_id=imported.get(repo.full_name),
        )
        for repo in repositories
        if (include_forks or not repo.fork) and (include_archived or not repo.archived)
    ]


@router.post("/repositories/import", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
async def import_repository(
    payload: ImportRepositoryRequest, user: CurrentUser, db: DbSession, request: Request
) -> RepositoryOut:
    """Import a GitHub repository so it can be analysed.

    Public repositories can be imported without a connected account; private
    ones require a token with the right scope, which is checked by GitHub itself.
    """
    if "/" not in payload.full_name:
        raise ValidationError("full_name must be in the form 'owner/repository'.")
    owner, name = payload.full_name.split("/", 1)

    account = (
        db.query(GitHubAccount)
        .filter(GitHubAccount.user_id == user.id)
        .order_by(GitHubAccount.created_at.desc())
        .first()
    )
    token = decrypt_secret(account.access_token_encrypted) if account else None

    remote = None
    languages: dict[str, int] = {}
    readme: str | None = None
    metadata_source = "github_api"
    api_error: str | None = None

    try:
        async with GitHubClient(token) as client:
            remote = await client.get_repository(owner, name)
            languages = await client.get_languages(owner, name)
            readme = await client.get_readme(owner, name)
    except RateLimitedError as exc:
        raise ServiceUnavailableError(str(exc)) from exc
    except GitHubError as exc:
        api_error = str(exc)

    if remote is None:
        # The REST API was unavailable (no OAuth app, an outage, or a network
        # policy that allows git but not api.github.com). A public repository can
        # still be analysed from its clone, so fall back to that rather than
        # refusing. The record is marked so the UI can say metadata is limited —
        # stars, topics and languages are left empty, never invented.
        clone_url = f"https://github.com/{owner}/{name}.git"
        probe = probe_public_repository(clone_url)
        if not probe.reachable:
            raise NotFoundError(
                f"Could not read {payload.full_name} from GitHub: {api_error or probe.error}. "
                "If it is private, connect a GitHub account with repository access."
            )
        metadata_source = "clone_only"
        remote = _minimal_remote(owner, name, clone_url, probe.default_branch or "main")

    candidate: Candidate | None = None
    if payload.candidate_id:
        candidate = db.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise NotFoundError("Candidate not found.")
        if user.role == "STUDENT" and candidate.user_id != user.id:
            raise ForbiddenError("You can only attach repositories to your own profile.")

    repository = (
        db.query(Repository)
        .filter(Repository.owner_user_id == user.id, Repository.full_name == remote.full_name)
        .first()
    ) or Repository(owner_user_id=user.id, full_name=remote.full_name, name=remote.name)

    repository.external_id = str(remote.id)
    repository.name = remote.name
    repository.description = remote.description
    repository.html_url = remote.html_url
    repository.clone_url = remote.clone_url
    repository.default_branch = remote.default_branch
    repository.is_private = remote.private
    repository.is_fork = remote.fork
    repository.is_archived = remote.archived
    repository.primary_language = remote.language
    repository.languages = languages
    repository.topics = remote.topics
    repository.stars = remote.stargazers_count
    repository.forks = remote.forks_count
    repository.open_issues = remote.open_issues_count
    repository.size_kb = remote.size_kb
    repository.license_name = remote.license_name
    repository.readme = readme
    repository.pushed_at = remote.pushed_at
    repository.repo_created_at = remote.created_at
    repository.repo_updated_at = remote.updated_at
    repository.github_account_id = account.id if account else None
    repository.github_metadata = {
        **remote.to_dict(),
        "metadata_source": metadata_source,
        "metadata_note": None if metadata_source == "github_api" else (
            "Imported from the git remote because the GitHub REST API was unavailable. Stars, "
            "topics, languages and the README are not populated; analysis is unaffected."
        ),
        "api_error": api_error,
    }
    if candidate is not None:
        repository.candidate_id = candidate.id
    elif not repository.candidate_id:
        own = db.query(Candidate).filter(Candidate.user_id == user.id).first()
        if own is not None:
            repository.candidate_id = own.id

    db.add(repository)
    audit.record(db, audit.ACTION_REPOSITORY_ACCESSED, actor=user, target_type="repository",
                 target_id=repository.id, detail={"full_name": remote.full_name, "action": "import"},
                 request=request)
    db.commit()
    db.refresh(repository)
    return RepositoryOut.model_validate(repository)


def _latest_analysis_id(db: Session, repository_id: str) -> str | None:
    row = (
        db.query(RepositoryAnalysis.id)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    return row[0] if row else None


def _minimal_remote(owner: str, name: str, clone_url: str, default_branch: str):
    """A GitHubRepository populated only with what git itself can confirm."""
    from repolens_github import GitHubRepository

    return GitHubRepository(
        id=0, name=name, full_name=f"{owner}/{name}", private=False,
        html_url=f"https://github.com/{owner}/{name}", clone_url=clone_url,
        default_branch=default_branch, owner_login=owner,
    )


@router.get("/repositories", response_model=Page[RepositoryOut])
def list_repositories(
    user: CurrentUser, db: DbSession,
    candidate_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[RepositoryOut]:
    query = db.query(Repository)
    if user.role == "ADMIN":
        pass
    elif user.role == "INTERVIEWER":
        organization_ids = user_organization_ids(db, user)
        candidate_ids = [
            row.id for row in
            db.query(Candidate.id).filter(Candidate.organization_id.in_(organization_ids)).all()
        ]
        query = query.filter(
            (Repository.owner_user_id == user.id) | (Repository.candidate_id.in_(candidate_ids))
        )
    else:
        query = query.filter(Repository.owner_user_id == user.id)

    if candidate_id:
        query = query.filter(Repository.candidate_id == candidate_id)

    total = query.count()
    rows = (
        query.order_by(Repository.last_analyzed_at.desc().nullslast(), Repository.created_at.desc())
        .limit(limit).offset(offset).all()
    )
    return Page(items=[RepositoryOut.model_validate(r) for r in rows],
                total=total, limit=limit, offset=offset)


@router.get("/repositories/{repository_id}", response_model=RepositoryOut)
def get_repository(repository_id: str, user: CurrentUser, db: DbSession) -> RepositoryOut:
    return RepositoryOut.model_validate(_visible_repository(db, user, repository_id))


@router.post("/repositories/{repository_id}/analyze", response_model=AnalysisJobOut,
             status_code=status.HTTP_202_ACCEPTED)
def analyze_repository(
    repository_id: str, payload: AnalyzeRequest, user: CurrentUser, db: DbSession, request: Request,
    _: Annotated[None, Depends(analysis_rate_limit)] = None,
) -> AnalysisJobOut:
    """Queue an analysis. Returns immediately; poll the job for progress."""
    repository = _visible_repository(db, user, repository_id)

    active = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.repository_id == repository.id,
            AnalysisJob.status.in_(["QUEUED", "RUNNING"]),
        )
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )
    if active is not None and not payload.force:
        return AnalysisJobOut.model_validate(active)

    job = AnalysisJob(
        repository_id=repository.id, requested_by_id=user.id, status="QUEUED",
        stages=initial_stages(),
        options={"force": payload.force, "compare_against_corpus": payload.compare_against_corpus},
    )
    db.add(job)
    repository.analysis_status = "QUEUED"
    db.add(repository)
    audit.record(db, audit.ACTION_REPOSITORY_ANALYZED, actor=user, target_type="repository",
                 target_id=repository.id, detail={"analysis_job": job.id, "action": "queued"},
                 request=request)
    db.commit()
    db.refresh(job)

    try:
        dispatch = enqueue(run_analysis_job, job.id)
    except RuntimeError as exc:
        job.status = "FAILED"
        job.error = str(exc)
        db.add(job)
        db.commit()
        raise ServiceUnavailableError(str(exc)) from exc

    job.job_id = dispatch.job_id
    job.worker = dispatch.backend
    db.add(job)
    db.commit()
    db.refresh(job)
    return AnalysisJobOut.model_validate(job)


@router.get("/repositories/{repository_id}/jobs", response_model=list[AnalysisJobOut])
def list_analysis_jobs(
    repository_id: str, user: CurrentUser, db: DbSession, limit: int = Query(default=10, ge=1, le=50)
) -> list[AnalysisJobOut]:
    repository = _visible_repository(db, user, repository_id)
    rows = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.repository_id == repository.id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(limit).all()
    )
    return [AnalysisJobOut.model_validate(r) for r in rows]


@router.get("/analysis-jobs/{job_id}", response_model=AnalysisJobOut)
def get_analysis_job(job_id: str, user: CurrentUser, db: DbSession) -> AnalysisJobOut:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise NotFoundError("Analysis job not found.")
    _visible_repository(db, user, job.repository_id)
    payload = AnalysisJobOut.model_validate(job)
    if job.status == "QUEUED":
        # A job that cannot start should say so rather than spin in the UI.
        status = backend_status()
        if status.get("note"):
            payload.error = status["note"]
    return payload


@router.post("/analysis-jobs/{job_id}/cancel", response_model=AnalysisJobOut)
def cancel_analysis_job(job_id: str, user: CurrentUser, db: DbSession) -> AnalysisJobOut:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise NotFoundError("Analysis job not found.")
    _visible_repository(db, user, job.repository_id)
    if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
        raise ValidationError(f"This job is already {job.status.lower()}.")
    job.status = "CANCELLED"
    job.finished_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    return AnalysisJobOut.model_validate(job)


@router.get("/repositories/{repository_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(
    repository_id: str, user: CurrentUser, db: DbSession, limit: int = Query(default=10, ge=1, le=50)
) -> list[AnalysisOut]:
    repository = _visible_repository(db, user, repository_id)
    rows = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository.id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .limit(limit).all()
    )
    return [AnalysisOut.model_validate(r) for r in rows]


@router.get("/repositories/{repository_id}/analysis", response_model=AnalysisDetailOut)
def latest_analysis(repository_id: str, user: CurrentUser, db: DbSession) -> AnalysisDetailOut:
    repository = _visible_repository(db, user, repository_id)
    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository.id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if analysis is None:
        raise NotFoundError("This repository has not been analysed yet.")
    return AnalysisDetailOut.model_validate(analysis)


@router.get("/repositories/{repository_id}/security", response_model=list[SecurityFindingOut])
def repository_security(
    repository_id: str, user: CurrentUser, db: DbSession,
    severity: str | None = None, limit: int = Query(default=200, ge=1, le=500),
) -> list[SecurityFindingOut]:
    repository = _visible_repository(db, user, repository_id)
    # Scoped to the most recent analysis: every run writes its own findings, and
    # unioning them across runs would report the same issue once per analysis.
    analysis = _latest_analysis_id(db, repository.id)
    query = db.query(SecurityFinding).filter(
        SecurityFinding.repository_id == repository.id,
        SecurityFinding.analysis_id == analysis,
    ) if analysis else db.query(SecurityFinding).filter(SecurityFinding.id.is_(None))
    if severity:
        query = query.filter(SecurityFinding.severity == severity)
    rows = query.order_by(SecurityFinding.confidence.desc()).limit(limit).all()
    return [SecurityFindingOut.model_validate(r) for r in rows]


@router.get("/repositories/{repository_id}/similarity", response_model=list[SimilarityOut])
def repository_similarity(
    repository_id: str, user: CurrentUser, db: DbSession,
    scope: str | None = None, limit: int = Query(default=100, ge=1, le=300),
) -> list[SimilarityOut]:
    repository = _visible_repository(db, user, repository_id)
    analysis = _latest_analysis_id(db, repository.id)
    query = db.query(SimilarityResult).filter(
        SimilarityResult.repository_id == repository.id,
        SimilarityResult.analysis_id == analysis,
    ) if analysis else db.query(SimilarityResult).filter(SimilarityResult.id.is_(None))
    if scope:
        query = query.filter(SimilarityResult.scope == scope)
    rows = query.order_by(SimilarityResult.similarity.desc()).limit(limit).all()
    return [SimilarityOut.model_validate(r) for r in rows]


@router.get("/repositories/{repository_id}/commits", response_model=list[CommitOut])
def repository_commits(
    repository_id: str, user: CurrentUser, db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CommitOut]:
    repository = _visible_repository(db, user, repository_id)
    rows = (
        db.query(RepositoryCommit)
        .filter(RepositoryCommit.repository_id == repository.id)
        .order_by(RepositoryCommit.committed_at.desc())
        .limit(limit).all()
    )
    return [CommitOut.model_validate(r) for r in rows]


@router.get("/repositories/{repository_id}/files", response_model=list[dict])
def repository_files(
    repository_id: str, user: CurrentUser, db: DbSession,
    category: str | None = None, limit: int = Query(default=500, ge=1, le=2000),
) -> list[dict]:
    """File inventory with classification. File *contents* are never served."""
    repository = _visible_repository(db, user, repository_id)
    query = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id)
    if category:
        query = query.filter(RepositoryFile.category == category)
    rows = query.order_by(RepositoryFile.size_bytes.desc()).limit(limit).all()
    return [
        {
            "path": r.path, "category": r.category, "language": r.language,
            "size_bytes": r.size_bytes, "line_count": r.line_count,
            "content_hash": r.content_hash[:12], "skipped_reason": r.skipped_reason,
        }
        for r in rows
    ]


@router.delete("/repositories/{repository_id}", response_model=Message)
def delete_repository(
    repository_id: str, user: CurrentUser, db: DbSession, request: Request
) -> Message:
    repository = _visible_repository(db, user, repository_id)
    if user.role != "ADMIN" and repository.owner_user_id != user.id:
        raise ForbiddenError("Only the owner of a repository can remove it.")
    full_name = repository.full_name
    db.delete(repository)
    audit.record(db, "repository.deleted", actor=user, target_type="repository",
                 target_id=repository_id, detail={"full_name": full_name}, request=request)
    db.commit()
    return Message(message=f"Removed {full_name} and all of its analyses.")
