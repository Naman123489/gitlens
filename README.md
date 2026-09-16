# RepoLens

**Know What a GitHub Profile Really Proves.**

RepoLens analyses GitHub repositories against a target job description and produces an
evidence-backed engineering evaluation: what the code demonstrates, how it was built, how
relevant it is to a role, and where a human should ask questions.

> RepoLens does not try to determine whether a candidate used AI. It determines whether the
> candidate demonstrates real engineering ability, ownership, relevance and understanding —
> regardless of the tools they used to build the software.

---

## What it does

| | |
| --- | --- |
| **Repository intelligence** | Tree-sitter AST analysis across Python, JavaScript, TypeScript, Java, C and C++: complexity, duplication, nesting, error handling, testing, documentation, dependencies and architecture. |
| **Engineering evolution** | Commit history read as a development story — implementation → fixes → refactoring → tests → documentation → deployment. |
| **Ownership confidence** | Positive evidence that the candidate built and maintained the code, computed from artefacts rather than from the absence of AI signals. |
| **AI usage analysis** | A probabilistic estimate of AI assistance with every signal named, every alternative explanation stated, and a confidence attached. |
| **AI utilization efficiency** | Whether AI appears to have been used *productively*. Low AI usage is not rewarded. |
| **Similarity** | Winnowing fingerprints, AST structural comparison and embeddings, plus tutorial/scaffold detection. |
| **Security** | Credential detection with entropy gating and injection-pattern analysis. Detected values are masked at the point of detection. |
| **Job matching** | Job descriptions parsed into weighted requirements, matched to dependency, import, language and structural evidence. |
| **Technical verification** | Interview questions generated from the repository's own functions, findings and history, with assessed answers and reviewer override. |

## What it refuses to do

1. **No automated rejection.** The strongest outcome is `VERIFICATION_REQUIRED`, which means
   "ask the candidate about this". There is no reject status, and the hiring decision belongs to
   a human.
2. **No claim that code was AI-generated.** That cannot be established from source code alone, so
   the system never asserts it. Every AI-origin figure is probabilistic and ships with its
   confidence, its signals and its limitations.
3. **No invented results.** An analyzer that fails marks its dimension unavailable with a reason.
   Nothing is substituted for a missing measurement.
4. **No protected characteristics.** Only technical evidence is analysed, stored or reported.
5. **No execution of candidate code.** Repositories are cloned read-only with hooks disabled.
   Nothing from a repository is ever installed, built or run.

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env          # optional: add GitHub OAuth and LLM credentials
docker compose up --build
```

- Web app → <http://localhost:3000>
- API docs → <http://localhost:8000/docs>

Migrations run automatically before the API starts.

### Without Docker

```bash
# 1. Dependencies
python -m venv .venv && source .venv/bin/activate
pip install -e packages/shared -e packages/analysis -e packages/github \
            -e packages/security -e packages/similarity -e packages/scoring -e apps/api
(cd apps/web && npm install)

# 2. Database (PostgreSQL 16+ and Redis 7+ must be running)
createdb repolens
(cd apps/api && alembic upgrade head)

# 3. Run: API, worker and web in separate terminals
(cd apps/api && uvicorn app.main:app --reload)
(cd apps/api && python -m app.workers.run_worker)
(cd apps/web && npm run dev)
```

Optional demo data:

```bash
python scripts/seed_demo.py       # synthetic candidates, jobs and policies
python scripts/create_admin.py --email you@example.com --generate-password
```

The seed creates accounts, jobs and repository links — **not** scores. Every score in RepoLens
comes from analysing real code, so run an analysis to see one.

## The workflow

```
Register → connect GitHub → import a repository → analyse
                                                     │
                            create a job ────────────┤
                                                     ▼
                                                evaluation
                             (weighted score, evidence, verification status)
                                                     │
                                    ┌────────────────┴───────────────┐
                                    ▼                                ▼
                        generated interview questions          exportable report
                                    │
                                    ▼
                         technical verification session
```

## Repository layout

```
repolens/
├── apps/
│   ├── api/          FastAPI: routing, auth, persistence, orchestration
│   │   ├── app/      core · db · models · schemas · api · services · workers · seed
│   │   ├── alembic/  migrations
│   │   └── tests/    155 tests, including synthetic-repository scenarios
│   └── web/          Next.js 15 · TypeScript · Tailwind · Recharts
├── packages/         Pure-Python analysis libraries (no web or DB imports)
│   ├── shared/       Evidence, scores, enums, analyzer versioning
│   ├── github/       GitHub REST + OAuth, safe repository fetching
│   ├── analysis/     Classification, AST, metrics, tests, docs, deps, history, AI, ownership
│   ├── security/     Secret and injection detection with masking
│   ├── similarity/   Fingerprints, structural comparison, embeddings, tutorial signals
│   └── scoring/      Skill taxonomy, JD parsing, matching, policies, scoring engine
├── infrastructure/   Dockerfiles and database bootstrap
├── docs/             Architecture, API, scoring, AI analysis, security, privacy, development
└── scripts/          Demo seed and admin provisioning
```

The analysis engine is deliberately separate from the API: every analyzer is importable and
testable without a database or an HTTP server.

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, schema, and known limitations |
| [SCORING.md](docs/SCORING.md) | How every score is computed, with the thresholds and weights |
| [AI_ANALYSIS.md](docs/AI_ANALYSIS.md) | What the AI-usage estimate is, how it works, and what it cannot do |
| [API.md](docs/API.md) | Endpoint reference, auth, errors and rate limits |
| [SECURITY.md](docs/SECURITY.md) | Threat model, sandboxing, credential handling |
| [PRIVACY.md](docs/PRIVACY.md) | What is collected, why, retention, and candidate rights |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local setup, testing, migrations, adding an analyzer |

## Tests

```bash
(cd apps/api && pytest)      # 155 tests
(cd apps/web && npm test)    #  21 tests
```

The suite includes four synthetic repositories built with real git histories, which assert that
RepoLens reaches the *right judgement* — not merely a number — on excellent engineering, an
unexplained code drop, a tutorial-derived scaffold, and AI-augmented work with strong ownership.

## Status

This is a working prototype. The end-to-end workflow runs against real repositories. Known
limitations are listed in [ARCHITECTURE.md](docs/ARCHITECTURE.md#known-limitations) and are
surfaced in the product itself wherever they affect a result.

## Licence

Not yet licensed for distribution.
