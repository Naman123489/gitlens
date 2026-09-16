"""The repository-analysis worker task.

Runs outside the request cycle, owns its own database session, and records
progress on the :class:`AnalysisJob` row so the UI can show live stage progress.

A failure here marks the job ``FAILED`` with a reason. It never leaves a job
stuck in ``RUNNING``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from repolens_analysis.limits import LimitExceeded
from repolens_github import FetchError

from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.db.session import session_scope
from app.models import AnalysisJob, Candidate, GitHubAccount, Repository
from app.services import audit
from app.services.pipeline import STAGES, run_pipeline

logger = get_logger("repolens.worker")


def initial_stages() -> list[dict[str, object]]:
    return [{"key": key, "label": label, "status": "pending", "progress": 0.0}
            for key, label in STAGES]


def run_analysis_job(analysis_job_id: str) -> None:
    """Entry point invoked by RQ (or the inline executor)."""
    started = time.perf_counter()
    with session_scope() as db:
        job = db.get(AnalysisJob, analysis_job_id)
        if job is None:
            logger.error("analysis_job_missing", analysis_job_id=analysis_job_id)
            return
        if job.status == "CANCELLED":
            logger.info("analysis_job_cancelled_before_start", analysis_job_id=analysis_job_id)
            return
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        job.stages = initial_stages()
        job.progress = 0.0
        repository_id = job.repository_id
        db.add(job)

    try:
        with session_scope() as db:
            job = db.get(AnalysisJob, analysis_job_id)
            repository = db.get(Repository, repository_id)
            if job is None or repository is None:  # pragma: no cover - deleted mid-flight
                return

            token, emails = _credentials(db, repository)

            def progress(stage_key: str, fraction: float, label: str) -> None:
                stages = job.stages or initial_stages()
                seen_current = False
                for stage in stages:
                    if stage["key"] == stage_key:
                        stage["status"] = "running"
                        stage["label"] = label
                        seen_current = True
                    elif not seen_current:
                        stage["status"] = "completed"
                        stage["progress"] = 1.0
                job.stages = list(stages)
                job.current_stage = label
                job.progress = round(fraction, 4)
                db.add(job)
                db.commit()

            outcome = run_pipeline(
                db=db, repository=repository, access_token=token, candidate_emails=emails,
                progress=progress, analysis_job_id=analysis_job_id,
            )

            for stage in job.stages or []:
                stage["status"] = "completed"
                stage["progress"] = 1.0
            job.stages = list(job.stages or [])
            job.status = "COMPLETED"
            job.progress = 1.0
            job.current_stage = "Completed"
            job.analysis_id = outcome.analysis.id
            job.finished_at = datetime.now(timezone.utc)
            job.duration_seconds = round(time.perf_counter() - started, 3)
            db.add(job)

            audit.record(
                db, audit.ACTION_REPOSITORY_ANALYZED, actor=None, target_type="repository",
                target_id=repository.id,
                detail={
                    "analysis_id": outcome.analysis.id,
                    "analyzer_failures": [f.analyzer for f in outcome.failures],
                    "duration_seconds": job.duration_seconds,
                },
            )
            logger.info("analysis_completed", repository=repository.full_name,
                        duration=job.duration_seconds, failures=len(outcome.failures))
    except (FetchError, LimitExceeded) as exc:
        _fail(analysis_job_id, repository_id, f"{type(exc).__name__}: {exc}", started)
    except Exception as exc:  # noqa: BLE001 - never leave a job running
        logger.exception("analysis_job_failed", analysis_job_id=analysis_job_id)
        _fail(analysis_job_id, repository_id, f"{type(exc).__name__}: {exc}"[:500], started)


def _credentials(db, repository: Repository) -> tuple[str | None, set[str]]:
    """Resolve the GitHub token and the candidate's known commit emails."""
    token: str | None = None
    emails: set[str] = set()
    account: GitHubAccount | None = None
    if repository.github_account_id:
        account = db.get(GitHubAccount, repository.github_account_id)
    elif repository.owner_user_id:
        account = (
            db.query(GitHubAccount)
            .filter(GitHubAccount.user_id == repository.owner_user_id)
            .order_by(GitHubAccount.created_at.desc())
            .first()
        )
    if account is not None:
        token = decrypt_secret(account.access_token_encrypted)
        emails.update(e.lower() for e in (account.verified_emails or []))
        if account.login:
            emails.add(f"{account.login.lower()}@users.noreply.github.com")
    if repository.candidate_id:
        candidate = db.get(Candidate, repository.candidate_id)
        if candidate and candidate.email:
            emails.add(candidate.email.lower())
    return token, emails


def _fail(analysis_job_id: str, repository_id: str, reason: str, started: float) -> None:
    with session_scope() as db:
        job = db.get(AnalysisJob, analysis_job_id)
        if job is not None:
            job.status = "FAILED"
            job.error = reason
            job.finished_at = datetime.now(timezone.utc)
            job.duration_seconds = round(time.perf_counter() - started, 3)
            db.add(job)
        repository = db.get(Repository, repository_id)
        if repository is not None:
            repository.analysis_status = "FAILED"
            db.add(repository)
