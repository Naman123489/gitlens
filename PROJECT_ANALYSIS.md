# PROJECT_ANALYSIS.md

Phase 0 inspection report for the RepoLens build.

## 1. State of the repository at the start of this work

The repository `naman123489/gitlens` was effectively empty:

```
.
├── .git/
└── README.md      (9 bytes: "# gitlens")
```

- Single commit on `main` (`e8e5967 Initial commit`).
- **No** existing framework, package manager, database, authentication, components or configuration.
- No `package.json`, no `pyproject.toml`, no CI configuration, no Docker files.

**Conclusion:** there is no working code to preserve and no established architecture to
respect, so Rule 10 ("do not rewrite the architecture unnecessarily") does not constrain us.
RepoLens is built greenfield using the reference architecture from the specification.

Despite the repository being named `gitlens`, it contains none of the GitKraken GitLens
source; the name collision is incidental. The product built here is **RepoLens**.

## 2. Verified toolchain in the build environment

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.11.15 | virtualenv at `.venv/` |
| Node.js | 22.22.2 | npm 10.9.7 available |
| PostgreSQL | 16.13 | running locally; `repolens` + `repolens_test` databases created |
| Redis | 7.0.15 | running locally |
| Docker | 29.3.1 | used for `docker-compose.yml` |
| tree-sitter | `tree-sitter-language-pack` | verified working for Python/JS/TS/Java/C/C++ |

Package installation from PyPI and npm both work through the environment proxy.

### Capability gap found during inspection

`pgvector` is **not** available in the locally installed PostgreSQL 16
(`pg_available_extensions` lists `pg_trgm` but no `vector`). This is handled explicitly
rather than faked:

- The vector store is an interface (`packages/similarity/repolens_similarity/vector_store.py`)
  with two implementations: a `pgvector` backend and a portable array backend that stores
  embeddings as `float[]` and computes cosine similarity in Python.
- `docker-compose.yml` uses the `pgvector/pgvector:pg16` image, so the pgvector path is the
  one exercised in the supported development environment.
- The limitation is documented in `docs/AI_ANALYSIS.md` and `docs/ARCHITECTURE.md`.

## 3. Architecture chosen

Monorepo, as described in the specification, with the analysis engine deliberately kept out
of the API layer:

```
repolens/
├── apps/
│   ├── api/          FastAPI: routing, auth, persistence, orchestration only
│   └── web/          Next.js 15 + TypeScript + Tailwind + Recharts
├── packages/         Pure-Python analysis libraries, no FastAPI/DB imports
│   ├── shared/       Evidence/Score primitives, enums, analyzer versioning
│   ├── github/       GitHub REST + OAuth client, caching, rate-limit handling
│   ├── analysis/     File classification, AST, metrics, tests, docs, deps, git history
│   ├── security/     Secret + injection detection with masking
│   ├── similarity/   Winnowing fingerprints, AST structural hashing, embeddings
│   └── scoring/      Deterministic weighted scoring and verification status
├── infrastructure/
├── docs/
└── scripts/
```

Each `packages/*` directory is an installable Python distribution. They are importable
without a database or an HTTP server, which is what makes the analyzers unit-testable
against synthetic repositories (see `apps/api/tests/`).

## 4. Key engineering decisions

1. **Deterministic first.** Every score is produced by deterministic static analysis and a
   documented weighted policy. The LLM layer is optional and can only *explain* evidence,
   never produce a score. With no `LLM_API_KEY` configured the system is fully functional;
   narrative text falls back to deterministic templates built from the same evidence.
2. **Probabilistic AI analysis, never definitive.** The AI-usage analyzer emits a likelihood,
   a confidence band, an explicit list of signals and an explicit list of limitations. There is
   no code path that can output "this code was written by AI".
3. **No candidate code is ever executed.** Repositories are fetched with
   `git clone --depth` into a temp directory with `core.hooksPath=/dev/null`, credentials
   disabled and size/file/time budgets enforced before and during walk. No dependency
   installation, no build, no test execution.
4. **Incremental analysis by content hash.** Every file's SHA-256 is persisted; unchanged
   files reuse the previous analysis rows.
5. **Async job engine with per-analyzer isolation.** A failing analyzer records a
   `analyzer_failures` entry and the evaluation continues, marked `ANALYSIS_INCOMPLETE`
   for that dimension. Results are never invented to fill a gap.
6. **Reproducibility.** Every evaluation records analyzer version, policy version, LLM model
   and prompt version. Historic evaluations are immutable.

## 5. Implementation plan (phases actually executed)

| Phase | Content |
| --- | --- |
| 1 | Monorepo, config, PostgreSQL schema + Alembic, JWT auth + RBAC, API skeleton, Docker |
| 2 | GitHub OAuth + REST client, repository listing, safe ingestion, file classification |
| 3 | AST engine, code metrics, testing/docs/dependency analyzers, security scanner, git history |
| 4 | Exact / structural / semantic similarity, tutorial-derivation signals |
| 5 | AI-assistance signals, AI utilization efficiency, ownership confidence, candidate disclosure |
| 6 | Job description parsing, skill taxonomy, requirement weights, evaluation policies |
| 7 | Deterministic scoring engine, evidence linking, verification status |
| 8 | Interviewer portal |
| 9 | Student portal |
| 10 | Repository-specific interview question generation and technical verification |
| 11 | Tests, rate limiting, audit logging, error handling, resource limits |
| 12 | UX polish, empty/loading states, responsive layout, documentation |

## 6. Things explicitly *not* implemented

These are declared rather than faked. Each has an isolated interface so it can be added later,
and each is documented in `docs/ARCHITECTURE.md` under "Known limitations":

- GitLab / Bitbucket / enterprise GitHub source providers (the `SourceProvider` protocol exists,
  only the GitHub implementation is supplied).
- Live CVE lookup for dependencies. The dependency analyzer reports counts, categories, pinning
  discipline and manifest hygiene; it does **not** claim vulnerabilities, because no reliable
  offline vulnerability database is bundled.
- Coverage percentages from real coverage runs (would require executing candidate code, which is
  forbidden). Test-to-source ratio and framework/CI detection are used instead.
- A crawled corpus of public tutorial repositories. Tutorial detection runs against a curated,
  auditable local signal set plus cross-candidate similarity, and reports `UNKNOWN` when it has
  insufficient reference material.
