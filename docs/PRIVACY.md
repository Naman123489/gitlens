# Privacy and responsible evaluation

RepoLens processes information about people applying for jobs. This document states exactly what
is collected, why, how long it is kept, and what a candidate can ask for.

## What is collected

| Data | Why | Source |
| --- | --- | --- |
| Email, name, password hash | Authentication | Registration |
| GitHub login, avatar, profile URL, verified emails | Attributing commits to the candidate | GitHub OAuth, with the candidate's consent |
| GitHub access token (encrypted) | Reading repositories the candidate selected | GitHub OAuth |
| Repository metadata — name, description, languages, stars, topics, timestamps | Context for the evaluation | GitHub API, or the git remote when the API is unavailable |
| File inventory — path, category, language, size, line count, SHA-256 | Analysis and incremental re-analysis | The clone |
| Commit metadata — sha, author name and email, timestamp, subject, line counts | Development-history analysis | The clone |
| Code chunks — function boundaries, fingerprints, embeddings | Similarity analysis | The clone |
| Analysis results, evidence, scores | The evaluation itself | Computed |
| Résumé text and extracted skills | Comparing claims with repository evidence | Uploaded by the candidate |
| AI disclosure | Context for the AI-usage analysis | Written by the candidate |
| Interview questions, answers, assessments | Technical verification | The session |
| Audit log entries | Accountability and reproducibility | Every consequential action |

### What is deliberately **not** collected

- Any protected or sensitive characteristic: race, religion, political affiliation, health,
  disability, sexuality, ethnicity, age, gender, nationality. These are never inferred, stored,
  displayed or used in any score.
- Personal data from repository content beyond commit authorship, which git records by design.
- Detected credential values. They are masked at the point of detection and the plaintext is
  never written anywhere.
- Raw file contents. Files are read in memory during analysis and discarded with the clone. What
  persists is metrics, hashes, function boundaries and short evidence snippets — and those
  snippets have any detected credential replaced with `[REDACTED]`.

## How repository data is processed

1. The repository is cloned read-only into a temporary directory. Hooks are disabled; nothing is
   executed, installed or built.
2. Files are classified. Vendored dependencies, build output and binaries are skipped.
3. Analyzers compute metrics over the text in memory.
4. The clone is deleted — including on failure.
5. What remains in the database is the derived analysis.

## Retention

| Data | Retention |
| --- | --- |
| Clone of a repository | Deleted at the end of the analysis run |
| Analysis results and evidence | Until the repository or account is deleted |
| Evaluations | Until deleted by the owning organisation |
| Audit log | Append-only; retained for accountability |
| GitHub token | Until the candidate disconnects the account |

Deleting a repository cascades to its files, commits, chunks, analyses, findings and evaluations.
Deleting an account cascades to everything owned by it.

## Access control

- A candidate sees their own repositories, analyses and evaluations.
- An interviewer sees candidates in their own organisation, and only those.
- Reviewer notes are interviewer-only unless explicitly shared with the candidate.
- An administrator can see operational data and audit logs.
- Requests for records outside the caller's scope return **404, not 403**, so the API does not
  confirm that a record exists.

## Candidate rights

| Right | How |
| --- | --- |
| See what was analysed | The student portal shows every score with the evidence behind it, including file and line references |
| Understand a score | Every dimension lists its sub-metrics, its evidence and how to improve it |
| Know the limits | Every analysis reports what it could not establish |
| Disclose AI use | Voluntary, written by the candidate, stored separately from inferred signals |
| Disconnect GitHub | One action; the stored token is deleted |
| Delete a repository | One action; cascades to all derived data |
| Contest a finding | An interviewer can override any score or status, with their rationale recorded alongside the original value |

## Responsible evaluation

These are product rules, enforced in code and asserted by tests:

1. **No automated rejection.** The strongest outcome is `VERIFICATION_REQUIRED`. There is no
   reject status and no code path that recommends rejecting anyone.
2. **No claim of AI authorship.** AI-origin results are probabilistic, carry a confidence, list
   every signal with its alternative explanation, and state their limitations.
3. **AI use is not misconduct.** The utilization score rewards effective augmentation.
4. **Absence of evidence is not evidence of absence.** Résumé gaps are reported as *verification
   recommended*, with an explicit note that work in private repositories or at an employer leaves
   no trace here.
5. **Similarity is not plagiarism.** Cross-repository matches say that shared open-source
   ancestry, a common idiom or a shared starter template are the most common explanations.
6. **The decision is a human's.** Reports carry the line: *this report is decision support, not a
   decision.*

## For deployers

If you run RepoLens against real candidates:

- Tell candidates their repositories will be analysed, and what for.
- Give them access to their own results; the student portal exists for this.
- Do not use RepoLens as an automated filter. It is built to inform a conversation.
- Review `ENABLE_DEMO_SEED` is off, and that demo records — always marked `is_demo` and using the
  reserved `@repolens.invalid` domain — never reach a production database.
- Automated evaluation of job applicants is regulated in some jurisdictions. Check your
  obligations before deploying.
