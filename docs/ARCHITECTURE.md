# Architecture

## Principles

1. **The analysis engine is not the API.** Everything in `packages/` is pure Python with no
   FastAPI, SQLAlchemy or network imports. Analyzers can be run against a directory from a REPL,
   which is what makes them testable against synthetic repositories.
2. **Deterministic by default.** Every score is arithmetic over measured values. An LLM may
   rewrite evidence into prose; it can never produce or alter a number.
3. **Missing is not zero.** A failed analyzer yields an unavailable dimension with a reason, and
   the scoring engine renormalises the remaining weights.
4. **Everything is versioned.** Analyzer version, scoring-engine version, policy version, prompt
   version and LLM model are recorded on every evaluation.

## System shape

```
                       ┌──────────────┐
                       │   Next.js    │  student · interviewer · admin portals
                       └──────┬───────┘
                              │ JSON over HTTPS, bearer tokens
                       ┌──────▼───────┐
                       │   FastAPI    │  auth · RBAC · validation · orchestration
                       └──┬────────┬──┘
              enqueue job │        │ read/write
                    ┌─────▼──┐  ┌──▼────────────┐
                    │ Redis  │  │  PostgreSQL   │  30 tables
                    └─────┬──┘  └──▲────────────┘
                          │        │
                    ┌─────▼────────┴──┐
                    │  RQ worker      │  runs the pipeline out of process
                    └─────┬───────────┘
                          │ imports
                    ┌─────▼───────────────────────────────────────┐
                    │ packages/  shared · github · analysis ·      │
                    │            security · similarity · scoring   │
                    └─────────────────────────────────────────────┘
```

## The analysis pipeline

`apps/api/app/services/pipeline.py` orchestrates thirteen stages. Each analyzer stage is wrapped
so that a failure is recorded and the run continues:

```
ingestion → discovery → AST → metrics → testing → documentation → dependencies
  → security → architecture → git history → similarity → AI & ownership → persist
```

**Ingestion** is pluggable behind a `SourceFetcher` protocol. The default implementation clones
over https with hooks disabled, credential helpers disabled, submodules skipped, a depth limit
and a wall-clock timeout, then checks the on-disk size before anything reads the tree. Adding
GitLab or a local-path provider means adding a fetcher, not relaxing the default one.

**Discovery** walks the tree, skipping vendored, build and binary paths, and classifies every
file as candidate code, test code, generated code, dependency code, configuration, documentation
or asset. Only candidate and test code counts as the candidate's work.

**Incremental analysis.** Every file's SHA-256 is persisted. A re-run compares hashes and reports
how many files were unchanged, so repeat analysis of a large repository does not repeat work that
cannot have changed.

**Isolation.** Analyzer exceptions become `AnalyzerFailure` records; database writes run inside
`SAVEPOINT`s so one bad row cannot abort the transaction and take the rest of the run with it.

## Scoring

Analyzer output → category scores → policy weighting → evaluation. See
[SCORING.md](SCORING.md) for the full arithmetic. The scoring engine takes typed
`AnalyzerResult` objects and a versioned `EvaluationPolicy`, and returns a `ScoredEvaluation`
carrying scores, evidence, limitations, failures, verification status and the versions used.

## Data model

Thirty tables in five groups:

| Group | Tables |
| --- | --- |
| Identity | `users`, `organizations`, `organization_members`, `candidates`, `github_accounts`, `oauth_states` |
| Repository | `repositories`, `repository_files`, `repository_commits`, `repository_branches`, `repository_dependencies`, `code_chunks` |
| Analysis | `repository_analyses`, `security_findings`, `similarity_results`, `analyzer_failures` |
| Evaluation | `evaluation_policies`, `jobs`, `job_requirements`, `evaluations`, `evaluation_scores`, `evidence`, `reviewer_notes`, `human_overrides`, `recommendations` |
| Interview & system | `interview_questions`, `interview_sessions`, `interview_answers`, `audit_logs`, `analysis_jobs` |

Two tables are deliberately immutable:

- **`repository_analyses`** — a re-analysis inserts a new row, so an evaluation always points at
  the data it was computed from.
- **`evaluation_policies`** — editing a policy inserts a new version and clears `is_current` on
  the old one. A two-year-old evaluation can still be explained with the rules that produced it.

`human_overrides` keeps both the machine value and the reviewer's, so an override annotates the
record rather than rewriting it.

## Background jobs

Redis + RQ in production. When Redis is unreachable the dispatcher falls back to a bounded thread
pool so a developer can run the product with `uvicorn` alone — and says so through
`backend_status()`, which the admin health page renders. A reachable Redis with no worker
listening is also reported: a queued job that cannot start says why instead of spinning.

## Frontend

Next.js App Router, client components against the JSON API, with a typed client in `lib/api.ts`
that refreshes expired access tokens once per failure and de-duplicates concurrent refreshes. The
design system is dark-first with semantic colour reserved for status. Every list has an empty
state; every dashboard has a skeleton.

## Known limitations

These are real and are surfaced in the product wherever they affect a result.

| Limitation | Why | Where it is stated |
| --- | --- | --- |
| **No line coverage** | Measuring it requires executing candidate code, which RepoLens never does. Test volume, breadth, framework and CI invocation are used instead. | Testing analyzer limitations |
| **No CVE data** | No vulnerability database is bundled, and asserting a CVE without reliable advisory data would be fabricated evidence. Dependency analysis reports counts, pinning and lock-file discipline only. | Dependency analyzer limitations |
| **Lexical, not neural, embeddings** | The built-in embedder is a feature-hashing vectoriser: real and deterministic, but it compares token distributions rather than meaning. A neural provider plugs into `EmbeddingProvider`. | Similarity analyzer limitations, admin analyzer page |
| **No public-internet similarity search** | Comparison is against this deployment's own corpus. An absence of matches is not proof of originality. | Similarity analyzer limitations |
| **No crawled tutorial corpus** | Tutorial detection uses a curated, auditable signal set plus cross-repository similarity, and returns `UNKNOWN` rather than `ORIGINAL` when evidence is thin. | Tutorial assessment limitations, admin analyzer page |
| **AST coverage is six languages** | Python, JavaScript, TypeScript/TSX, Java, C and C++. Other languages are counted by line and marked `parsed=False`, so "no functions found" is never read as "this file has no functions". | Code-metrics limitations, admin analyzer page |
| **pgvector optional** | Available in the Docker image. Without it, cosine similarity is computed in Python — correct but linear, so prototype-scale only. | Admin health page |
| **Only GitHub** | A `SourceFetcher` protocol exists; only the GitHub implementation is supplied. | This document |
| **Answer assessment is shallow without an LLM** | The deterministic assessor measures coverage, specificity, repository consistency, depth markers and structure. It cannot judge whether an explanation is technically correct, and says so on every assessment. The reviewer's score always overrides it. | Every answer assessment |

## Extension points

| To add | Implement |
| --- | --- |
| GitLab, Bitbucket, enterprise GitHub | A `SourceFetcher` in `packages/github` |
| A language | A tree-sitter grammar entry in `languages.py`; the AST engine is language-agnostic |
| A neural embedder | `EmbeddingProvider` in `packages/similarity/embeddings.py` |
| An analyzer | Return an `AnalyzerResult`; register it in the pipeline and map it to a `ScoreCategory` |
| A vulnerability feed | A dependency-advisory client; the dependency analyzer already carries the shape for it |
