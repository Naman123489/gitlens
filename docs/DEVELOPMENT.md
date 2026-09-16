# Development

## Prerequisites

Python 3.11+, Node.js 20+, PostgreSQL 16+, Redis 7+, git. Docker is optional but is the fastest
route to a working environment.

## Setup

```bash
git clone <this repository> && cd repolens
cp .env.example .env

python -m venv .venv && source .venv/bin/activate
pip install -e packages/shared -e packages/analysis -e packages/github \
            -e packages/security -e packages/similarity -e packages/scoring \
            -e "apps/api[dev]"

createdb repolens && createdb repolens_test
(cd apps/api && alembic upgrade head)

(cd apps/web && npm install)
```

## Running

```bash
(cd apps/api && uvicorn app.main:app --reload)        # API      → :8000
(cd apps/api && python -m app.workers.run_worker)      # worker
(cd apps/web && npm run dev)                           # web app  → :3000
```

Or `docker compose up --build`, which also runs migrations.

Without a worker, analyses queue and never start — and the job's `error` field says exactly that.

## Tests

```bash
(cd apps/api && pytest)                 # 155 tests
(cd apps/api && pytest -k scenarios)    # the four synthetic-repository judgements
(cd apps/web && npm test)               #  21 component tests
(cd apps/web && npm run typecheck)
(cd apps/web && npm run build)
```

Database tests use `repolens_test` and skip cleanly when PostgreSQL is unreachable. Each test runs
in a transaction that is rolled back afterwards.

### The scenario tests

`apps/api/tests/fixtures.py` builds four real git repositories on disk:

| Fixture | Shape | Expected judgement |
| --- | --- | --- |
| `excellent` | Iterative development, tests, CI, docs, releases | High quality and ownership, low AI signals |
| `dropped` | Twelve uniform modules in a single commit | Weak ownership, assistance signals fire |
| `tutorial` | Unmodified `create-next-app` scaffold with attribution | Tutorial similarity detected |
| `augmented` | Assistance artefacts *plus* real iteration, tests and CI | Effective augmentation, ownership preserved |

These assert that RepoLens reaches the right *judgement*, not merely that it emits a number. If
you change an analyzer and one of them fails, the analyzer's judgement changed — work out which
answer is right before touching the threshold.

## Migrations

```bash
cd apps/api
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
alembic downgrade -1          # verify the down path before committing
```

The migration environment reads `DATABASE_URL` from application settings, so migrations and the
service can never disagree about which database they target.

## Adding an analyzer

1. Write it in `packages/analysis` (or a new package) returning an `AnalyzerResult`:

   ```python
   def analyze_thing(data: ThingInput) -> AnalyzerResult:
       result = AnalyzerResult(analyzer="thing", version="1.0.0")
       result.score = 72.5
       result.confidence = 0.8
       result.metrics = {"measured": 12, "sub_scores": {...}, "weights": {...}}
       result.add(Evidence(
           category=ScoreCategory.TECHNICAL_QUALITY,
           claim="A specific, checkable statement",
           severity=Severity.MEDIUM,
           confidence=0.9,
           supports="weakness",
           evidence=(EvidenceDetail(detail="what was observed", file="src/x.py", line=42),),
       ))
       result.limit("scope", "What this analyzer cannot establish.")
       return result
   ```

2. Call it from a `run_stage(...)` in `pipeline.py` so a failure is isolated.
3. Map it in `ANALYZER_CATEGORY` if it feeds a scored dimension.
4. Test it against the synthetic repositories.

**Rules.** Return `score=None` rather than guessing. Attach evidence to every claim. State
limitations. Keep it deterministic — an LLM may explain your output, never produce it.

## Adding a skill to the taxonomy

One entry in `packages/scoring/repolens_scoring/taxonomy.py`:

```python
_s("rust", "Rust", D.SYSTEMS, aliases=("rustlang",), languages=("rust",),
   dependencies=("tokio", "serde"), path_patterns=(r"Cargo\.toml$",)),
```

Every skill declares how it can be *evidenced*, which is what lets a job match be explained.

## Configuration

`.env.example` documents every variable. Notable ones:

| Variable | Effect |
| --- | --- |
| `ALLOW_INLINE_WORKER` | Run analyses on a thread pool when Redis is down. Convenient locally; set false in production so an outage is visible. |
| `GITHUB_REQUEST_PRIVATE_REPOS` | Requests the `repo` scope. Leave false unless private analysis is required. |
| `LLM_API_KEY` | Enables narrative prose and LLM-assisted answer assessment. Scores are unaffected either way. |
| `ENABLE_DEMO_SEED` | Never enable in production. |

The API refuses to start in production while `JWT_SECRET` or `ENCRYPTION_KEY` hold their
development defaults.

## Conventions

- Python: full type annotations, Pydantic models at the boundary, services between routers and
  the database, structured logging via `structlog`.
- TypeScript: strict mode, no `any` in component props, the typed client in `lib/api.ts` as the
  only place that talks to the API.
- Comments explain *why*. The code already says what.
- Every user-facing string about AI, similarity or verification is subject to the product rules
  in [AI_ANALYSIS.md](AI_ANALYSIS.md). Tests assert the wording.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Analyses stay `QUEUED` | No worker is listening. Start `python -m app.workers.run_worker`; the job's `error` field and the admin health page both say so. |
| `pgvector not installed` on the admin page | Expected outside Docker. Similarity still works; cosine is computed in Python. |
| GitHub import fails with 403 | The REST API is unreachable or unauthorised. Public repositories still import through the git remote, with metadata marked limited. |
| Tests skip | PostgreSQL is not reachable at `DATABASE_URL`. |
| `Slot failed to slot onto its children` | A `<Button asChild>` was given more than one child. |
