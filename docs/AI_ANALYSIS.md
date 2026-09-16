# AI usage analysis

Read this before changing anything in `packages/analysis/repolens_analysis/ai_usage.py`.

## The claim RepoLens makes — and the one it does not

**It does not claim to detect AI-generated code.** There is no reliable way to determine from
source code alone that a particular line came from a language model. Every published detector
has false positives on human code and false negatives on generated code, and the gap widens as
models improve.

**It estimates an assistance likelihood** from a set of named, individually weak signals, and
reports that estimate with its confidence, the signals that fired, and the legitimate non-AI
explanation for each one.

The strongest statement the system is capable of making is: *the available evidence suggests
substantial dependence on generated code with limited evidence of candidate-authored
development.* That is a prompt to have a conversation. It is not a finding of misconduct.

## Why this is framed as it is

AI-assisted development is legitimate professional practice. The useful question at hiring time
is not *did you use a tool* but *can you demonstrate that you understand, own and can maintain
this system*. RepoLens is built around the second question:

- Ownership confidence is computed from **positive evidence of engineering work**, not from the
  absence of AI signals. A repository with no AI signals and no tests still scores badly on
  ownership.
- The AI-utilization score rewards **effective augmentation**. It does not reward low AI usage,
  and there is a leverage bonus for strong signals combined with strong ownership.
- No verification status is reachable from AI signals alone when ownership is strong.

## The signals

Seven signals, weighted to sum to 1. Each one is weak on its own; the estimate is their weighted
mean.

| Signal | Weight | What fires it | Legitimate non-AI explanation |
| --- | --- | --- | --- |
| Repository appeared with little incremental history | 0.20 | Single commit, or one commit holding >70% of all changed lines, or no iteration after the first version | Importing existing work in one commit, or squashing history, produces the same shape |
| Style discontinuity between files | 0.14 | Some files sit far from the repository's own style baseline | A second contributor, a copied module, or an editor's auto-format |
| Uniform, exhaustive documentation on trivial code | 0.14 | Nearly every function carries a structured docstring, including trivial ones, while project documentation is thin | Disciplined developers and docstring linters do this too |
| Repetitive near-identical implementations | 0.12 | Multiple functions share an identical control-flow shape with only names changed | Code generators, framework conventions, CRUD scaffolding |
| Inconsistent abstraction level | 0.12 | Sophisticated constructs beside markedly naive ones | Normal in a codebase written over a long period, or while learning |
| Assistant-style artefacts in source | 0.16 | Narration comments, step markers, "your code here", markdown fences, "Example usage:" blocks | Copied documentation and tutorial code produce identical artefacts |
| Large volume added in very short periods | 0.12 | Days where the repository grew many times its own median | A focused work session, a merge, a vendored import |

Each firing signal is shown in the UI with its strength, its weight, the specific observation
that triggered it, and its alternative explanation.

## Confidence

Confidence is in the **estimate**, not in an authorship claim. It rises with the amount of
evidence available and is capped at 0.8 — the method does not admit certainty.

```
confidence = clamp(0.25 + 0.4 × data_quality + 0.25 × evidence_breadth, 0, 0.8)
```

`data_quality` counts commit history, style profiles, entity count and text availability;
`evidence_breadth` is the fraction of signals that fired at all.

## Classification

The classification combines likelihood with **ownership confidence**, because the same signals
mean different things depending on what else the repository shows.

| Likelihood | Ownership ≥ 70 | Ownership 45–70 | Ownership < 45 |
| --- | --- | --- | --- |
| < 35 | AI-assisted | AI-assisted | AI-assisted |
| 35–60 | AI-assisted | AI-augmented | AI-augmented |
| 60–78 | AI-augmented | AI-dependent | AI-dependent |
| ≥ 78 | AI-augmented | AI-dependent | AI-dominated |

With no ownership evidence available at all, the result is `INSUFFICIENT_EVIDENCE` — never a
negative classification.

| Classification | Meaning |
| --- | --- |
| **AI-assisted** | Consistent with AI used for support tasks — debugging, boilerplate, documentation, test scaffolding — with ownership demonstrated |
| **AI-augmented** | AI generated meaningful components which the candidate integrated, modified and maintained |
| **AI-dependent** | A substantial share carries assistance signals and ownership evidence is limited; a conversation is recommended |
| **AI-dominated** | Evidence suggests substantial dependence with limited evidence of candidate-authored development; a prompt for verification, not a conclusion about the candidate |

## Candidate disclosure

Candidates may voluntarily record what they used AI for. The disclosure is stored **separately**
from the inferred signals and the two are compared, never conflated:

| Alignment | Meaning |
| --- | --- |
| `consistent` | The declaration and the signals do not conflict |
| `declared_more_than_observed` | The candidate declared use the artefacts do not show — assistance used for debugging, learning or review leaves little trace in code |
| `signals_above_declaration` | Signals are stronger than the disclosure suggests; these signals have legitimate non-AI explanations, so this is a conversation topic, not evidence of a false statement |

Only the candidate can write their own disclosure. An interviewer filling it in on someone's
behalf would make it worthless as a statement, so the API refuses.

## Rules enforced by tests

`apps/api/tests/test_scoring_scenarios.py` asserts:

- The AI-usage output never contains "was written by", "ai-generated code", "definitely",
  "proves" or "cheat".
- Every AI-usage result carries limitations, one of which states the figure is a probabilistic
  estimate.
- Similarity output never contains "cheat", "plagiari", "dishonest", "fake" or "fraud".
- A repository with strong assistance signals *and* strong ownership scores better on utilization
  than one with the same signals and weak ownership.
- Strong AI signals with strong ownership produce `CLEAR`, not an escalation.

## Repository D

The test suite builds a repository designed to carry strong assistance artefacts — uniform
`Args:`/`Returns:` docstrings, repetitive service modules, step-numbered comments, an
"Example usage" block — alongside genuine engineering: a bug-fix commit that explains a real
concurrency problem, tests covering the failure path, CI, a performance change and a decisions
document.

It scores roughly 45/100 assistance likelihood with ownership around 74, classified
**AI-augmented**, with utilization around 60 — versus a repository with similar signals and no
development history, which reaches ownership 27 and utilization 24.

Same signals. Different evidence of ownership. Different outcome. That is the whole design.
