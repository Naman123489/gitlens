"""The repository analysis pipeline.

Orchestration only: every unit of analysis lives in ``packages/`` and is called
from here. The pipeline's own responsibilities are

* acquiring the repository safely,
* deciding what needs re-analysis (content hashing),
* running each analyzer in isolation so one failure cannot destroy the run,
* persisting results, evidence, findings and chunks,
* reporting progress.

An analyzer that raises is recorded as a failure with a reason and its category
is marked unavailable. Nothing is ever substituted for a missing result.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

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
    classify_intent,
    parse_dependencies,
    parse_file,
    profile_file,
    style_discontinuity,
    walk_repository,
)
from repolens_analysis.limits import AnalysisLimits, LimitExceeded
from repolens_github import FetchError, clone_repository
from repolens_security import SecurityInput, analyze_security
from repolens_shared import AnalyzerResult, ScoreCategory
from repolens_shared.versioning import ANALYZER_VERSION
from repolens_similarity import HashingEmbedder, SimilarityInput, analyze_similarity
from repolens_scoring import AnalyzerFailure

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import (
    AnalyzerFailureRecord,
    CodeChunk,
    Repository,
    RepositoryAnalysis,
    RepositoryBranch,
    RepositoryCommit,
    RepositoryDependency,
    RepositoryFile,
    SecurityFinding,
    SimilarityResult,
)
from app.services import vectors

logger = get_logger("repolens.pipeline")

#: The ordered stages reported to the UI.
STAGES: tuple[tuple[str, str], ...] = (
    ("ingestion", "Repository ingestion"),
    ("discovery", "File discovery and classification"),
    ("ast", "AST analysis"),
    ("metrics", "Code quality metrics"),
    ("testing", "Testing analysis"),
    ("documentation", "Documentation analysis"),
    ("dependencies", "Dependency analysis"),
    ("security", "Security analysis"),
    ("architecture", "Architecture analysis"),
    ("git", "Git history analysis"),
    ("similarity", "Similarity analysis"),
    ("ai_usage", "AI and ownership analysis"),
    ("persist", "Persisting results"),
)

#: Which score category each analyzer feeds, for failure reporting.
ANALYZER_CATEGORY: dict[str, ScoreCategory] = {
    "code_metrics": ScoreCategory.TECHNICAL_QUALITY,
    "testing": ScoreCategory.TESTING,
    "documentation": ScoreCategory.DOCUMENTATION,
    "dependencies": ScoreCategory.ARCHITECTURE,
    "security": ScoreCategory.SECURITY,
    "architecture": ScoreCategory.ARCHITECTURE,
    "git_history": ScoreCategory.GIT_ENGINEERING,
    "ownership": ScoreCategory.OWNERSHIP,
    "ai_utilization": ScoreCategory.AI_UTILIZATION,
}

ProgressCallback = Callable[[str, float, str], None]


@dataclass(slots=True)
class PipelineOutcome:
    analysis: RepositoryAnalysis
    results: dict[str, AnalyzerResult]
    failures: list[AnalyzerFailure]
    stats: dict[str, Any]
    duration_seconds: float


@dataclass(slots=True)
class _Context:
    """Everything the analyzers share, assembled once."""

    texts: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    languages: dict[str, str | None] = field(default_factory=dict)
    all_paths: list[str] = field(default_factory=list)
    asts: list[Any] = field(default_factory=list)
    reused_files: int = 0


def _noop(_: str, __: float, ___: str) -> None:
    return None


@contextmanager
def savepoint(db: Session, what: str) -> Iterator[bool]:
    """Run a database write inside a SAVEPOINT.

    Without this, one bad row (an over-long value, a constraint violation) aborts
    the whole transaction and every later stage fails with
    ``PendingRollbackError``. The savepoint confines the damage to the single
    write that failed, which is exactly the per-analyzer isolation the pipeline
    promises.
    """
    try:
        with db.begin_nested():
            yield True
    except Exception as exc:  # noqa: BLE001 - isolation is the point
        logger.error("persist_failed", what=what, error=f"{type(exc).__name__}: {exc}"[:300])


def run_pipeline(
    db: Session,
    repository: Repository,
    access_token: str | None = None,
    candidate_emails: set[str] | None = None,
    verification_score: float | None = None,
    progress: ProgressCallback | None = None,
    analysis_job_id: str | None = None,
    corpus_enabled: bool = True,
) -> PipelineOutcome:
    """Analyse one repository end to end and persist the result."""
    settings = get_settings()
    report = progress or _noop
    started = time.perf_counter()
    limits = AnalysisLimits(
        max_repository_bytes=settings.max_repository_mb * 1024 * 1024,
        max_files=settings.max_files_per_repository,
        max_file_bytes=settings.max_file_kb * 1024,
        analysis_timeout_seconds=settings.analysis_timeout_seconds,
        clone_timeout_seconds=settings.clone_timeout_seconds,
    )

    results: dict[str, AnalyzerResult] = {}
    failures: list[AnalyzerFailure] = []
    stats: dict[str, Any] = {}

    def run_stage(
        key: str, label: str, index: int, analyzer: str, category: ScoreCategory | None,
        fn: Callable[[], AnalyzerResult | None],
    ) -> AnalyzerResult | None:
        report(key, index / len(STAGES), label)
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            digest = sha256(traceback.format_exc().encode()).hexdigest()[:16]
            reason = f"{type(exc).__name__}: {exc}"[:400]
            logger.error("analyzer_failed", analyzer=analyzer, repository=repository.full_name,
                         reason=reason, digest=digest)
            failures.append(AnalyzerFailure(
                analyzer=analyzer, category=category, reason=reason,
                occurred_at=datetime.now(timezone.utc).isoformat(),
            ))
            db.add(AnalyzerFailureRecord(
                created_at=datetime.now(timezone.utc), analysis_job_id=analysis_job_id,
                repository_id=repository.id, analyzer=analyzer,
                category=str(category) if category else None, reason=reason,
                traceback_digest=digest,
            ))
            return None

    # -- 1. acquire ----------------------------------------------------------
    report("ingestion", 0.0, "Repository ingestion")
    if not repository.clone_url:
        raise FetchError("repository has no clone URL")
    fetched = clone_repository(
        repository.clone_url, token=access_token, branch=repository.default_branch or None,
        timeout=limits.clone_timeout_seconds, max_bytes=limits.max_repository_bytes,
    )

    try:
        context = _Context()
        with fetched:
            # -- 2. discovery -------------------------------------------------
            report("discovery", 1 / len(STAGES), "File discovery and classification")
            walk = walk_repository(fetched.path, limits=limits)
            context.all_paths = [f.path for f in walk.files]
            for repo_file in walk.files:
                context.categories[repo_file.path] = str(repo_file.category)
                context.languages[repo_file.path] = repo_file.language
                if repo_file.text is not None:
                    context.texts[repo_file.path] = repo_file.text

            stats["files"] = {
                "total_seen": walk.total_files_seen,
                "analysed": len(walk.files),
                "ignored": walk.ignored_files,
                "bytes": walk.total_bytes,
                "by_category": walk.by_category(),
                "truncated": walk.truncated,
                "notes": walk.notes,
            }

            # -- 3. AST (incremental by content hash) --------------------------
            report("ast", 2 / len(STAGES), "AST analysis")
            previous = {
                row.path: row for row in
                db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id).all()
            }
            for repo_file in walk.files:
                if repo_file.text is None or not repo_file.is_source:
                    continue
                file_ast = parse_file(
                    repo_file.path, repo_file.text, repo_file.language or "text",
                    limits=limits, keep_source=True,
                )
                context.asts.append(file_ast)
                prior = previous.get(repo_file.path)
                if prior is not None and prior.content_hash == repo_file.content_hash:
                    context.reused_files += 1
            stats["ast"] = {
                "files_parsed": sum(1 for a in context.asts if a.parsed),
                "files_unparsed": sum(1 for a in context.asts if not a.parsed),
                "entities": sum(len(a.entities) for a in context.asts),
                "unchanged_since_last_run": context.reused_files,
            }

            # -- 4-11. analyzers ----------------------------------------------
            metrics = run_stage(
                "metrics", "Code quality metrics", 3, "code_metrics",
                ScoreCategory.TECHNICAL_QUALITY,
                lambda: analyze_metrics(MetricsInput(asts=context.asts, texts=context.texts)),
            )
            if metrics:
                results["code_metrics"] = metrics

            testing = run_stage(
                "testing", "Testing analysis", 4, "testing", ScoreCategory.TESTING,
                lambda: analyze_testing(TestingInput(
                    texts=context.texts, categories=context.categories,
                    asts=context.asts, all_paths=context.all_paths,
                )),
            )
            if testing:
                results["testing"] = testing

            documented_ratio = float(
                (metrics.metrics.get("documented_function_ratio", 0.0) if metrics else 0.0)
            )
            documentation = run_stage(
                "documentation", "Documentation analysis", 5, "documentation",
                ScoreCategory.DOCUMENTATION,
                lambda: analyze_documentation(DocumentationInput(
                    texts=context.texts, all_paths=context.all_paths,
                    documented_function_ratio=documented_ratio,
                )),
            )
            if documentation:
                results["documentation"] = documentation

            dependencies = run_stage(
                "dependencies", "Dependency analysis", 6, "dependencies", ScoreCategory.ARCHITECTURE,
                lambda: analyze_dependencies(DependencyInput(
                    texts=context.texts, all_paths=context.all_paths,
                )),
            )
            if dependencies:
                results["dependencies"] = dependencies

            has_lock = any(
                p.rsplit("/", 1)[-1].lower() in
                {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
                 "cargo.lock", "go.sum", "pipfile.lock"}
                for p in context.all_paths
            )
            security = run_stage(
                "security", "Security analysis", 7, "security", ScoreCategory.SECURITY,
                lambda: analyze_security(SecurityInput(
                    texts=context.texts, languages=context.languages,
                    all_paths=context.all_paths, has_lock_file=has_lock,
                )),
            )
            if security:
                results["security"] = security

            architecture = run_stage(
                "architecture", "Architecture analysis", 8, "architecture", ScoreCategory.ARCHITECTURE,
                lambda: analyze_architecture(ArchitectureInput(
                    asts=context.asts, all_paths=context.all_paths,
                    texts=context.texts, categories=context.categories,
                )),
            )
            if architecture:
                results["architecture"] = architecture

            # -- git history ---------------------------------------------------
            report("git", 9 / len(STAGES), "Git history analysis")
            history_signals = None
            try:
                history = collect_history(fetched.path, limits=limits)
                git_result, history_signals = analyze_git_history(history, candidate_emails)
                results["git_history"] = git_result
                with savepoint(db, "git_history"):
                    _persist_git(db, repository, history)
            except Exception as exc:  # noqa: BLE001
                reason = f"{type(exc).__name__}: {exc}"[:400]
                logger.error("analyzer_failed", analyzer="git_history", reason=reason)
                failures.append(AnalyzerFailure(
                    analyzer="git_history", category=ScoreCategory.GIT_ENGINEERING,
                    reason=reason, occurred_at=datetime.now(timezone.utc).isoformat(),
                ))
            if history_signals is None:
                from repolens_analysis import HistorySignals

                history_signals = HistorySignals()

            # -- similarity ----------------------------------------------------
            report("similarity", 10 / len(STAGES), "Similarity analysis")
            chunks: list[Any] = []
            similarity = None
            try:
                corpus = vectors.load_corpus(db, repository.id) if corpus_enabled else []
                similarity, chunks = analyze_similarity(SimilarityInput(
                    asts=context.asts, texts=context.texts, categories=context.categories,
                    repository_id=repository.id, corpus=corpus,
                    embedder=HashingEmbedder(settings.embedding_dimensions),
                ))
                results["similarity"] = similarity
            except Exception as exc:  # noqa: BLE001
                reason = f"{type(exc).__name__}: {exc}"[:400]
                logger.error("analyzer_failed", analyzer="similarity", reason=reason)
                failures.append(AnalyzerFailure(
                    analyzer="similarity", category=None, reason=reason,
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                ))

            # -- AI usage and ownership ----------------------------------------
            report("ai_usage", 11 / len(STAGES), "AI and ownership analysis")
            profiles = [
                profile_file(a, context.texts[a.path])
                for a in context.asts
                if a.path in context.texts and context.categories.get(a.path) == "CANDIDATE_CODE"
            ]
            discontinuity, _ = style_discontinuity(profiles)

            ownership_input = _build_ownership_input(
                history_signals=history_signals, metrics=metrics, testing=testing,
                documentation=documentation, dependencies=dependencies, security=security,
                architecture=architecture, similarity=similarity,
                style_discontinuity=discontinuity, verification_score=verification_score,
                source_file_count=sum(
                    1 for c in context.categories.values() if c == "CANDIDATE_CODE"
                ),
                context=context,
            )

            ownership = run_stage(
                "ai_usage", "Ownership analysis", 11, "ownership", ScoreCategory.OWNERSHIP,
                lambda: analyze_ownership(ownership_input),
            )
            if ownership:
                results["ownership"] = ownership

            ai_usage = run_stage(
                "ai_usage", "AI usage analysis", 11, "ai_usage", None,
                lambda: analyze_ai_usage(
                    AIUsageInput(
                        asts=context.asts, texts=context.texts, categories=context.categories,
                        history=history_signals,
                        duplication_ratio=float(metrics.metrics.get("duplication_ratio", 0.0)) if metrics else 0.0,
                        structural_clone_groups=len(
                            (similarity.metrics.get("structural_clone_groups") or []) if similarity else []
                        ),
                        documented_function_ratio=documented_ratio,
                        readme_words=int(documentation.metrics.get("readme_words", 0)) if documentation else 0,
                        test_cases=int(testing.metrics.get("test_cases", 0)) if testing else 0,
                    ),
                    ownership_confidence=ownership.score if ownership else None,
                ),
            )
            if ai_usage:
                results["ai_usage"] = ai_usage
                ownership_input.ai_likelihood = float(
                    ai_usage.metrics.get("estimated_ai_assistance", 0.0)
                )

            utilization = run_stage(
                "ai_usage", "AI utilization efficiency", 11, "ai_utilization",
                ScoreCategory.AI_UTILIZATION,
                lambda: analyze_ai_utilization(ownership_input, ownership.score if ownership else 0.0),
            )
            if utilization:
                results["ai_utilization"] = utilization

            # -- persist --------------------------------------------------------
            report("persist", 12 / len(STAGES), "Persisting results")
            analysis = _persist_analysis(
                db=db, repository=repository, results=results, failures=failures, stats=stats,
                head_sha=fetched.head_sha, analysis_job_id=analysis_job_id,
                duration=time.perf_counter() - started,
            )
            with savepoint(db, "files"):
                _persist_files(db, repository, walk)
            with savepoint(db, "dependencies"):
                _persist_dependencies(db, repository, context.texts)
            with savepoint(db, "chunks"):
                _persist_chunks(db, repository, chunks, settings.embedding_dimensions)
            if security:
                with savepoint(db, "security_findings"):
                    _persist_security(db, repository, analysis, security)
            if similarity:
                with savepoint(db, "similarity_results"):
                    _persist_similarity(db, repository, analysis, similarity)

            repository.last_analyzed_at = datetime.now(timezone.utc)
            repository.last_analyzed_sha = fetched.head_sha
            repository.analysis_status = "COMPLETED"
            db.add(repository)
            db.flush()

            return PipelineOutcome(
                analysis=analysis, results=results, failures=failures, stats=stats,
                duration_seconds=time.perf_counter() - started,
            )
    except LimitExceeded as exc:
        repository.analysis_status = "FAILED"
        db.add(repository)
        raise
    finally:
        fetched.cleanup()


def _build_ownership_input(
    *, history_signals, metrics, testing, documentation, dependencies, security, architecture,
    similarity, style_discontinuity: float, verification_score: float | None,
    source_file_count: int, context: _Context,
) -> OwnershipInput:
    test_paths = [p for p, c in context.categories.items() if c == "TEST_CODE"]
    source_stems = {
        p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        for p, c in context.categories.items() if c == "CANDIDATE_CODE"
    }
    references_own = any(
        any(stem in context.texts.get(path, "").lower() for stem in source_stems if len(stem) > 3)
        for path in test_paths
    )
    return OwnershipInput(
        history=history_signals,
        test_cases=int(testing.metrics.get("test_cases", 0)) if testing else 0,
        test_files=len(test_paths),
        references_own_modules=references_own,
        readme_words=int(documentation.metrics.get("readme_words", 0)) if documentation else 0,
        readme_is_placeholder=bool(documentation.metrics.get("placeholder_readme")) if documentation else False,
        readme_features=sum(
            1 for v in (documentation.metrics.get("features") or {}).values() if v
        ) if documentation else 0,
        style_discontinuity=style_discontinuity,
        documented_function_ratio=float(metrics.metrics.get("documented_function_ratio", 0.0)) if metrics else 0.0,
        verification_score=verification_score,
        source_file_count=source_file_count,
        architecture_score=architecture.score if architecture else None,
        import_cycles=len((architecture.metrics.get("import_cycles") or [])) if architecture else 0,
        ci_runs_tests=bool(testing.metrics.get("ci_runs_tests")) if testing else False,
        error_handling_per_function=float(
            metrics.metrics.get("error_handling_per_function", 0.0)
        ) if metrics else 0.0,
        security_score=security.score if security else None,
        dependency_score=dependencies.score if dependencies else None,
        documentation_score=documentation.score if documentation else None,
    )


def _persist_analysis(
    *, db: Session, repository: Repository, results: dict[str, AnalyzerResult],
    failures: list[AnalyzerFailure], stats: dict[str, Any], head_sha: str | None,
    analysis_job_id: str | None, duration: float,
) -> RepositoryAnalysis:
    evidence = [
        {"id": e.evidence_id(), "analyzer": result.analyzer, **e.to_dict()}
        for result in results.values() for e in result.evidence
    ]
    limitations = [
        {"analyzer": result.analyzer, "scope": l.scope, "detail": l.detail}
        for result in results.values() for l in result.limitations
    ]
    category_scores = {
        str(category): {
            "score": results[name].score,
            "confidence": results[name].confidence,
            "analyzer": name,
        }
        for name, category in ANALYZER_CATEGORY.items()
        if name in results and results[name].score is not None
    }
    ai_usage = results.get("ai_usage")
    ownership = results.get("ownership")
    utilization = results.get("ai_utilization")
    similarity = results.get("similarity")

    analysis = RepositoryAnalysis(
        repository_id=repository.id,
        analysis_job_id=analysis_job_id,
        head_sha=head_sha,
        analyzer_version=ANALYZER_VERSION,
        results={name: result.to_dict() for name, result in results.items()},
        category_scores=category_scores,
        evidence=evidence,
        limitations=limitations,
        failures=[f.to_dict() for f in failures],
        stats=stats,
        duration_seconds=round(duration, 3),
        repository_score=_repository_score(category_scores),
        ownership_confidence=ownership.score if ownership else None,
        ai_likelihood=float(ai_usage.metrics.get("estimated_ai_assistance")) if ai_usage else None,
        ai_classification=str(ai_usage.metrics.get("classification")) if ai_usage else None,
        ai_utilization=utilization.score if utilization else None,
        originality=str(similarity.metrics.get("originality")) if similarity else None,
        is_partial=bool(failures) or any(r.partial for r in results.values()),
    )
    db.add(analysis)
    db.flush()
    return analysis


def _repository_score(category_scores: dict[str, Any]) -> float | None:
    """Job-independent repository score: the mean of the available categories.

    The job-weighted score is computed later by the scoring engine; this value
    exists so a repository can be ranked before any job is chosen.
    """
    values = [c["score"] for c in category_scores.values() if c.get("score") is not None]
    return round(sum(values) / len(values), 2) if values else None


def _persist_files(db: Session, repository: Repository, walk) -> None:
    db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id).delete()
    db.bulk_save_objects([
        RepositoryFile(
            repository_id=repository.id, path=f.path[:1000], category=str(f.category),
            language=f.language, size_bytes=f.size_bytes, line_count=f.line_count,
            content_hash=f.content_hash, skipped_reason=f.skipped_reason,
        )
        for f in walk.files
    ])


def _persist_git(db: Session, repository: Repository, history) -> None:
    if not history.available:
        return
    db.query(RepositoryCommit).filter(RepositoryCommit.repository_id == repository.id).delete()
    db.query(RepositoryBranch).filter(RepositoryBranch.repository_id == repository.id).delete()
    db.bulk_save_objects([
        RepositoryCommit(
            repository_id=repository.id, sha=commit.sha, author_name=commit.author_name[:200],
            author_email=commit.author_email[:320], committed_at=commit.committed_at,
            subject=commit.subject[:500], intent=classify_intent(commit.message),
            insertions=commit.insertions, deletions=commit.deletions,
            files_changed=commit.files_changed, is_merge=commit.is_merge,
        )
        for commit in history.commits[:2000]
    ])
    db.bulk_save_objects([
        RepositoryBranch(
            repository_id=repository.id, name=name[:300],
            is_default=name == history.default_branch,
        )
        for name in dict.fromkeys(history.branches[:100])
    ])


def _persist_dependencies(db: Session, repository: Repository, texts: dict[str, str]) -> None:
    from repolens_analysis.dependencies import categorize

    db.query(RepositoryDependency).filter(
        RepositoryDependency.repository_id == repository.id
    ).delete()
    dependencies = parse_dependencies(texts)
    categories = categorize(dependencies)
    category_by_name = {
        name: category for category, names in categories.items() for name in names
    }
    db.bulk_save_objects([
        RepositoryDependency(
            repository_id=repository.id, name=dependency.name[:200],
            version_spec=dependency.version_spec[:120], ecosystem=dependency.ecosystem,
            manifest=dependency.manifest[:500], is_dev=dependency.dev,
            is_pinned=dependency.pinned, category=category_by_name.get(dependency.name),
        )
        for dependency in dependencies[:1000]
    ])


def _persist_chunks(db: Session, repository: Repository, chunks: list[Any], dimensions: int) -> None:
    db.query(CodeChunk).filter(CodeChunk.repository_id == repository.id).delete()
    db.bulk_save_objects([
        CodeChunk(
            repository_id=repository.id, file_path=chunk.file[:1000], symbol=chunk.symbol[:300],
            language=chunk.language[:40], start_line=chunk.start_line, end_line=chunk.end_line,
            structure_signature=chunk.structure_signature, fingerprints=chunk.fingerprints[:400],
            embedding=[round(v, 6) for v in chunk.embedding], embedder=f"hashing-v1:{dimensions}",
        )
        for chunk in chunks[:5000]
    ])


def _persist_security(
    db: Session, repository: Repository, analysis: RepositoryAnalysis, result: AnalyzerResult
) -> None:
    db.bulk_save_objects([
        SecurityFinding(
            analysis_id=analysis.id, repository_id=repository.id,
            kind=finding.get("kind", "pattern"), rule_id=finding["rule_id"][:80],
            title=finding["title"][:300], category=finding.get("category"),
            severity=finding["severity"], confidence=float(finding.get("confidence", 0.0)),
            file_path=finding.get("file", "")[:1000], line=int(finding.get("line", 0)),
            masked_value=finding.get("masked_value"), snippet=finding.get("snippet"),
            remediation=finding.get("remediation"), cwe=finding.get("cwe"),
            note=finding.get("note"),
        )
        for finding in (result.metrics.get("findings") or [])[:400]
    ])


def _persist_similarity(
    db: Session, repository: Repository, analysis: RepositoryAnalysis, result: AnalyzerResult
) -> None:
    rows: list[SimilarityResult] = []
    for match in (result.metrics.get("internal_matches") or [])[:100]:
        left, right = str(match["left"]), str(match["right"])
        rows.append(SimilarityResult(
            analysis_id=analysis.id, repository_id=repository.id, scope="internal",
            mechanism=str(match.get("mechanism", "fingerprint")),
            similarity=float(match["similarity"]),
            source_file=left.split(":")[0][:1000], source_symbol=left.split(":")[-1][:300],
            matched_file=right.split(":")[0][:1000], matched_symbol=right.split(":")[-1][:300],
            details=match,
        ))
    for match in (result.metrics.get("external_matches") or [])[:100]:
        rows.append(SimilarityResult(
            analysis_id=analysis.id, repository_id=repository.id, scope="external",
            mechanism="combined", similarity=float(match["similarity"]),
            source_file=str(match.get("file", ""))[:1000],
            source_symbol=str(match.get("symbol", ""))[:300],
            matched_repository_id=match.get("matched_repository_id"),
            matched_repository_name=str(match.get("matched_repository", ""))[:300],
            matched_file=str(match.get("matched_file", ""))[:1000],
            matched_symbol=str(match.get("matched_symbol", ""))[:300],
            details=match,
        ))
    db.bulk_save_objects(rows)
