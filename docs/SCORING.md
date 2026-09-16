# Scoring

Every number RepoLens produces is arithmetic over measured values. This document is the full
specification: given a repository, you can reproduce any score by hand.

## The chain

```
analyzers → sub-metrics → category score → policy weights → overall score
                               │
                               └→ evidence (the observations behind it)
```

## Categories

Nine scored dimensions, each produced by a named analyzer:

| Category | Analyzer | What it measures |
| --- | --- | --- |
| `technical_quality` | `code_metrics` | Complexity, function size, nesting, duplication, naming, comments, error handling, modularity |
| `architecture` | `architecture` + `dependencies` | Layering, modularity, coupling, structure depth, entry points, dependency hygiene |
| `job_relevance` | `job_matching` | Evidence of the job's required skills |
| `ownership` | `ownership` | Positive evidence the candidate built and maintained the code |
| `testing` | `testing` | Test presence, volume, breadth, CI, coverage configuration |
| `documentation` | `documentation` | README completeness, length, examples, limitations, decisions |
| `git_engineering` | `git_history` | Commit volume, cadence, message quality, commit size, branching, releases |
| `security` | `security` | Credential exposure and insecure patterns |
| `ai_utilization` | `ai_utilization` | Whether AI appears to have been used productively |

## Sub-metric weights

### Technical quality

| Sub-metric | Weight | Good | Bad |
| --- | --- | --- | --- |
| Complexity | 0.24 | avg 3.0 | avg 12.0 |
| Function size | 0.16 | avg 20 lines | avg 90 lines |
| Nesting | 0.12 | depth 3 | depth 8 |
| Duplication | 0.16 | 2% | 25% |
| Naming | 0.10 | 90% descriptive | 50% |
| Comments | 0.08 | 6–35% of lines | <2% or >60% |
| Error handling | 0.08 | 0.12 constructs/function | 0 |
| Modularity | 0.06 | no oversized files | many files >600 lines |

Complexity is McCabe: one plus each decision point (`if`, loop, `except`/`catch`, `case`,
ternary, short-circuit operator). Duplication normalises each line — comments stripped, string
contents replaced, whitespace removed — then hashes six-line windows, so renaming a variable
does not hide a copy.

### Testing

| Sub-metric | Weight |
| --- | --- |
| Presence of test cases | 0.30 |
| Volume (test-to-source line ratio, best at 0.35) | 0.25 |
| Breadth (unit 0.45 · integration 0.35 · e2e 0.20) | 0.20 |
| CI runs the tests | 0.15 |
| Coverage tracking configured | 0.10 |

Line coverage is never estimated — see [ARCHITECTURE.md](ARCHITECTURE.md#known-limitations).

### Documentation

Ten weighted features (overview 0.14, setup 0.20, usage 0.16, architecture 0.14, API 0.10,
configuration 0.08, screenshots 0.05, contributing 0.04, limitations 0.05, decisions 0.04),
multiplied by a length gate (0.35 under 60 words, 1.0 over 400) and halved again if scaffold
placeholder text remains. Supporting docs and documented functions add up to 18 points.

### Git engineering

Volume 0.18, cadence 0.20, message quality 0.22, commit size 0.15, branching 0.12, releases 0.13.

Commit-size scoring rewards incremental commits. **This is a hygiene judgement, never an
authorship judgement**: importing existing work in one commit is a normal publishing pattern, and
the evidence says so explicitly.

### Architecture

Layering 0.32, modularity 0.24, coupling 0.22, structure depth 0.12, entry points 0.10. Layering
is inferred from directory conventions; coupling from an import graph built by resolving AST
imports against the repository's own files, so third-party imports never inflate it.

### Security

Starts at 100. Each finding subtracts `severity_penalty × confidence_weight`, where
`confidence_weight = (confidence − 0.3) / 0.7` — a low-confidence finding costs almost nothing.

| Severity | Penalty |
| --- | --- |
| Critical | 30 |
| High | 16 |
| Medium | 7 |
| Low | 2.5 |

A committed `.env` costs a flat 25. Good practices add back: `.env` ignored (+6), `.env.example`
present (+4), security policy (+3), lock file (+3).

### Ownership

Eight factors of positive evidence. **Factors that cannot be assessed are excluded from the
denominator, not scored as zero** — absence of data is not absence of ownership.

| Factor | Weight |
| --- | --- |
| Incremental development | 0.20 |
| Bug fixes and refactoring after v1 | 0.18 |
| Tests written for this codebase | 0.14 |
| Documentation specific to this project | 0.12 |
| Commit messages that describe intent | 0.12 |
| Consistent style across the codebase | 0.08 |
| Commits attributed to the candidate | 0.10 |
| Candidate explained the code under questioning | 0.06 |

Commit and active-day counts use a logarithmic curve, because the difference between 2 and 10
commits says far more about how a project was built than the difference between 32 and 40.

### AI utilization efficiency

Measures whether AI was used *productively*, not whether it was avoided.

| Factor | Weight |
| --- | --- |
| Verification (tests, CI, error handling, security) | 0.22 |
| Integration (files changed after first appearing) | 0.20 |
| Architectural ownership | 0.18 |
| Delivery | 0.15 |
| Demonstrable understanding | 0.15 |
| Dependency discipline | 0.10 |

A **leverage bonus** of +6 applies when assistance signals are strong (≥45) *and* ownership is
strong (≥65) *and* the base score is ≥55: getting more done with a tool while keeping ownership
is the behaviour the product wants to reward.

## Job relevance

Each requirement carries an importance weight summing to 1 across the job. For each skill the
matcher looks for evidence, strongest source first:

| Source | Contribution |
| --- | --- |
| Pipeline observation (git history present, tests counted, CI found) | 0.50 |
| Declared dependency | 0.45 |
| Language share of the codebase | up to 0.90 |
| Source import | 0.35 |
| Path convention | 0.35 |
| Repository topic | 0.15 |
| README mention | 0.10 |
| Description mention | 0.08 |

Contributions accumulate and clamp at 1.0. A skill is *matched* at ≥0.2.

```
job_relevance = 100 × Σ(strength × importance) / Σ(importance)
```

A README mention alone can never exceed 0.10 — anyone can write a word in a README.

## Overall score

```
overall = Σ(category_score × weight) / Σ(weight)        over available categories only
```

Unavailable categories are dropped from both sums. Confidence is the weighted mean of each
category's confidence, discounted by how much of the policy's weight was available:

```
confidence = part_confidence × (0.55 + 0.45 × coverage)
```

### Default policy

| Category | Weight |
| --- | --- |
| Technical quality | 20% |
| Job relevance | 20% |
| Architecture | 15% |
| Ownership | 15% |
| Testing | 10% |
| Documentation | 5% |
| Git engineering | 5% |
| Security | 5% |
| AI utilization | 5% |

Three presets ship alongside it: relevance-weighted (hiring for a stack), ownership-weighted
(internship and graduate hiring) and production-readiness (senior hiring). Teams define their
own; weights need not sum to 1 because they are normalised.

## Verification status

Advisory, never a decision.

| Status | Meaning |
| --- | --- |
| `CLEAR` | No ownership, similarity or completeness concerns were raised |
| `REVIEW_RECOMMENDED` | Something is worth a short conversation |
| `VERIFICATION_REQUIRED` | The artefacts alone cannot establish ownership; ask the candidate |
| `ANALYSIS_INCOMPLETE` | Too few dimensions were computed to draw a conclusion |

Triggers (thresholds are policy-configurable):

| Condition | Result |
| --- | --- |
| Ownership < 45% | Verification required |
| Ownership < 65% | Review recommended |
| External similarity ≥ 0.75 | Verification required |
| External similarity ≥ 0.55 | Review recommended |
| Strong tutorial similarity | Verification required |
| AI likelihood ≥ 65 **and** classification is dependent/dominated | Verification required |
| AI likelihood ≥ 65 with no disclosure | Review recommended |
| More than 2 résumé claims without evidence | Review recommended |
| Fewer than 4 categories available | Analysis incomplete |

**Strong AI signals with strong ownership produce `CLEAR`.** That combination is effective
augmentation, and there is a test asserting it stays that way.

There is no rejection status. `CHEATER`, `FAKE`, `AI_CHEATER` and `AUTOMATIC_REJECT` do not exist
in the codebase, and a test asserts they never will.

## Reproducing a score

Every evaluation records `analyzer_version`, `scoring_engine`, `policy_version`, `prompt_version`
and `llm_model`. Combined with the immutable analysis row and the immutable policy version, any
historic score can be recomputed and explained. Re-analysis never rewrites a past evaluation.
