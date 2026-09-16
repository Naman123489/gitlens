# API reference

Base URL: `/api/v1`. Interactive documentation: `/docs`. Machine-readable schema:
`/openapi.json`.

## Authentication

Bearer tokens:

```
Authorization: Bearer <access_token>
```

Access tokens last 60 minutes; refresh tokens last 14 days. The access token is also accepted
from the `repolens_session` cookie, which the OAuth redirect sets.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create an account (`STUDENT` or `INTERVIEWER` only) |
| POST | `/auth/login` | Sign in |
| POST | `/auth/refresh` | Exchange a refresh token for a new access token |
| POST | `/auth/logout` | Clear the session cookie |
| GET | `/auth/me` | Current user, organisations, GitHub accounts, candidate id |
| GET | `/auth/github/authorize` | Start the GitHub OAuth handshake |
| GET | `/auth/github/callback` | Complete it; the token is encrypted server-side |
| DELETE | `/auth/github/{account_id}` | Disconnect a GitHub account |

## Repositories and analysis

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/github/repositories` | List the caller's repositories on GitHub |
| POST | `/repositories/import` | Import `owner/name`; falls back to the git remote if the REST API is unavailable |
| GET | `/repositories` | Imported repositories visible to the caller |
| GET | `/repositories/{id}` | One repository |
| DELETE | `/repositories/{id}` | Remove it and all derived data |
| POST | `/repositories/{id}/analyze` | Queue an analysis (202, returns the job) |
| GET | `/repositories/{id}/jobs` | Analysis jobs for this repository |
| GET | `/repositories/{id}/analysis` | Latest analysis with results and evidence |
| GET | `/repositories/{id}/analyses` | Analysis history |
| GET | `/repositories/{id}/security` | Security findings from the latest analysis |
| GET | `/repositories/{id}/similarity` | Similarity results from the latest analysis |
| GET | `/repositories/{id}/commits` | Commit metadata |
| GET | `/repositories/{id}/files` | File inventory with classification (never file contents) |
| GET | `/analysis-jobs/{id}` | Job status with per-stage progress |
| POST | `/analysis-jobs/{id}/cancel` | Cancel a queued or running job |

Analysis is asynchronous. `POST /repositories/{id}/analyze` returns immediately; poll
`/analysis-jobs/{id}` for `stages`, `progress` and `current_stage`. If the queue is reachable but
no worker is listening, the job's `error` field says so rather than leaving the client spinning.

## Jobs

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/jobs/parse` | Parse a description without saving it |
| POST | `/jobs` | Create a job; the description is parsed into weighted requirements |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{id}` | One job with its requirements |
| PATCH | `/jobs/{id}` | Update; re-parses when the description or requirements change |
| DELETE | `/jobs/{id}` | Delete the job; existing evaluations are retained |
| GET | `/jobs/taxonomy/skills` | The skill taxonomy with each skill's evidence sources |

## Evaluations

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/evaluations` | Score an analysed repository against a job under a policy |
| GET | `/evaluations` | List, filterable by job, candidate, repository, status, minimum score |
| GET | `/evaluations/{id}` | Full evaluation: scores, skill matches, DNA, narrative, recommendations |
| GET | `/evaluations/{id}/evidence` | Evidence, filterable by category and by strength/weakness |
| GET/POST | `/evaluations/{id}/notes` | Reviewer notes |
| GET/POST | `/evaluations/{id}/overrides` | Human overrides; the original value is preserved |
| POST | `/evaluations/compare` | Side-by-side comparison of 2–6 evaluations |
| DELETE | `/evaluations/{id}` | Delete an evaluation |

## Candidates

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/candidates` | Add a candidate (interviewer only) |
| GET | `/candidates` | List candidates in the caller's organisation |
| GET | `/candidates/{id}` | Profile with repositories, evaluations and summary. Audited. |
| POST | `/candidates/{id}/resume` | Upload a PDF, Markdown or text résumé |
| GET | `/candidates/{id}/disclosure` | AI disclosure and its comparison with repository signals |
| PUT | `/candidates/{id}/disclosure` | Record a disclosure (the candidate only) |

## Interviews

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/interviews` | Create a session; questions are generated from the repository |
| GET | `/interviews` | List sessions |
| GET | `/interviews/{id}` | Session with questions and answers |
| POST | `/interviews/{id}/questions` | Generate additional questions |
| POST | `/interviews/{id}/answers` | Submit an answer; returns its assessment |
| POST | `/interviews/{id}/answers/{answer_id}/review` | Record the reviewer's own score, which overrides the automatic one |
| POST | `/interviews/{id}/complete` | Close the session and compute the verification score |

## Policies, student portal, reports, admin

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/policies/presets` | Built-in weightings |
| GET/POST | `/policies` | List or create; creating with an existing name adds a version |
| GET | `/policies/{id}/versions` | Full version history |
| GET | `/me/dashboard` | Student overview: engineering score, DNA, repositories, recommendations |
| GET | `/me/readiness` | Readiness across role archetypes, or against one job |
| GET | `/me/recommendations` | De-duplicated improvement plan |
| GET | `/reports/{evaluation_id}` | Full report as JSON |
| GET | `/reports/{evaluation_id}/markdown` | Downloadable Markdown report |
| GET | `/admin/health` | Dependencies, throughput, analyzer failures, versions |
| GET | `/admin/analyzers` | Analyzer configuration, security rules, limits |
| GET | `/admin/audit-logs` | Audit log |
| GET | `/admin/jobs` | Analysis job monitoring |
| GET | `/admin/analyzer-failures` | Analyzers that failed inside successful runs |
| GET | `/admin/users` | User administration |

## Errors

Every error has the same shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Repository not found.",
    "detail": {},
    "request_id": "cc6d720aa36e45c1"
  }
}
```

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `unauthorized` | Missing, invalid or expired token |
| 403 | `forbidden` | Authenticated but not permitted |
| 404 | `not_found` | Missing — or outside your scope, which is deliberately indistinguishable |
| 409 | `conflict` | Conflicts with existing data |
| 422 | `validation_error` | Invalid payload; `detail.errors` lists field, message and type |
| 429 | `rate_limited` | Over the limit; `Retry-After` is set |
| 503 | `service_unavailable` | A dependency (GitHub, the queue, the database) is unavailable |

Validation errors never echo the submitted value, so a rejected password is not returned.

`x-request-id` and `x-response-time-ms` are set on every response, and the request id appears in
both the error body and the structured logs.

## Rate limits

| Scope | Limit |
| --- | --- |
| All `/api/v1` requests | 120 per minute per identity |
| Repository analysis | 20 per hour per account |

Enforced in Redis where available, with an in-process fallback that the admin health endpoint
reports honestly as non-distributed.
