# Security

## Threat model

RepoLens processes **untrusted input by design**: candidate repositories are arbitrary code from
the internet, and résumés are arbitrary uploaded files.

| Threat | Mitigation |
| --- | --- |
| Malicious repository executes code during analysis | Nothing from a repository is ever executed, installed or built. Clones run with `core.hooksPath=/dev/null`, credential helpers disabled, `protocol.ext.allow=never`, `GIT_TERMINAL_PROMPT=0` and submodules skipped. |
| Repository exhausts worker resources | Depth-limited clone, wall-clock timeout, on-disk size check before the tree is read, and per-run budgets: 256 MB, 12 000 files, 1 MB per file, 512 KB for AST parsing, 5 000 commits, 15-minute analysis timeout. |
| Symlink escape during the walk | `os.walk(followlinks=False)`; symlinks are skipped, not followed. |
| Repository URL points somewhere unexpected | Only `https://` remotes are clonable. `file://` and `ssh://` are refused. Alternative sources require implementing a `SourceFetcher`, not relaxing this rule. |
| Worker compromise | In Docker the worker runs read-only, with `no-new-privileges`, all capabilities dropped, a 2 GB memory limit and a `tmpfs` as the only writable path. |
| Credentials leak into the database or UI | Secrets are masked at the point of detection. `SecretFinding.masked_value` keeps at most two characters; the snippet has the value replaced with `[REDACTED]`. The raw value never leaves the scanner. |
| Stored GitHub tokens exposed | Encrypted at rest with Fernet (AES-128-CBC + HMAC) under a key derived from `ENCRYPTION_KEY`. Decrypted only inside the worker and the GitHub service. Never serialised into any response — there is a test asserting the shape of `/auth/me`. |
| Token leaks through git error output | Clone failures are redacted before they are logged or raised. |
| Malicious résumé upload | Size-capped, parsed with `pypdf` in a try/except, and a PDF with no text layer produces a clear error rather than an empty parse. |
| Credential stuffing | bcrypt hashing; a dummy hash is checked when the account does not exist so timing does not reveal existence; sign-in failures return an identical message either way. |
| Weak passwords | Minimum 10 characters, must mix character classes, must use at least 5 distinct characters, and must not be built on a commonly guessed base — checked after stripping leetspeak and digit suffixes, so `password123` and `p4ssw0rd!` are both rejected. |
| Privilege escalation via sign-up | The registration schema accepts only `STUDENT` and `INTERVIEWER`. Administrators are provisioned with `scripts/create_admin.py`. |
| Cross-tenant data access | Every repository, candidate and evaluation lookup is scoped to the caller's organisation membership. Non-members receive **404, not 403**, so the API does not confirm that a record exists. |
| Analysis abuse | 120 requests/minute per identity and 20 analyses/hour per account, enforced in Redis where available. |
| Insecure production configuration | The API refuses to start in production while `JWT_SECRET` or `ENCRYPTION_KEY` hold their development defaults, `DEBUG` is on, or CORS is a wildcard. |

## What the security analyzer does

Two scanners run over the analysed tree.

**Credential detection.** Thirteen high-precision provider patterns (AWS, GitHub, Slack, Stripe,
Google, OpenAI, Anthropic, private-key blocks, JWTs, credentialed connection strings, Twilio,
SendGrid) plus one generic `KEY = "value"` rule gated on Shannon entropy ≥ 3.2. A curated
placeholder list suppresses `changeme`, `your-api-key-here`, `${VAR}`, `os.environ[...]` and
similar. Findings in example, template and test paths keep a reduced confidence and carry a note
explaining why, rather than being silently dropped.

**Insecure patterns.** Nineteen rules across SQL injection, command injection, unsafe
evaluation and deserialisation, XSS, disabled TLS verification, weak hashing, plaintext password
comparison, disabled JWT verification, permissive CORS with credentials, and path traversal. Each
carries a severity, a calibrated confidence, a CWE reference and a remediation.

Pattern scanning runs on **code and configuration only**. Documentation quotes code constantly —
a changelog entry describing `verify=False` is prose, not a vulnerability — so scanning it
produced noise and was removed. Credential scanning still covers every file, because a leaked
key in a README is a real leaked key.

### What it is not

Pattern-based static analysis without data-flow or taint tracking. It surfaces code worth a human
review; it neither proves exploitability nor guarantees the absence of vulnerabilities. Every
result says so. Third-party dependency vulnerabilities are explicitly out of scope: no CVE
database is bundled, and claiming vulnerabilities without reliable advisory data would be
fabricated evidence.

## Authentication

Short-lived JWT access tokens (60 minutes) with longer-lived refresh tokens (14 days), signed
HS256 with a required `exp`, `sub`, `type` and issuer. Access tokens are also accepted from an
`HttpOnly` cookie so the OAuth redirect can establish a session without exposing a token to
JavaScript. A refresh token cannot be used as an access token, and vice versa.

### GitHub OAuth

Minimum scopes: `read:user user:email`, plus `repo` only when `GITHUB_REQUEST_PRIVATE_REPOS` is
enabled. CSRF state is stored server-side with a 15-minute expiry and is single-use. The access
token is exchanged, encrypted and stored server-side; the browser receives a RepoLens session and
never the GitHub token.

## Audit logging

Append-only, written in the same transaction as the action it describes. Covered: evaluation
creation and scoring, reviewer overrides (with both the original and the new value), reviewer
notes, report generation, repository access and analysis, candidate creation and access, GitHub
connect and disconnect, policy creation and updates, job creation, sign-in, registration,
interview creation and scoring, and disclosure updates.

## Reporting a vulnerability

This is a prototype and has not been through external review. If you find something, open an
issue describing the impact and how to reproduce it; do not include live credentials.
