import {
  ArrowRight,
  Boxes,
  FileSearch,
  GitBranch,
  Github,
  Lock,
  MessagesSquare,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Connect a repository",
    detail:
      "Authorise GitHub, or point RepoLens at any public repository. It is cloned read-only into " +
      "a sandbox. Nothing from the repository is ever executed, installed or built.",
  },
  {
    step: "02",
    title: "Analyse the evidence",
    detail:
      "Tree-sitter parses the code; deterministic analyzers measure complexity, tests, docs, " +
      "dependencies, security patterns, architecture and the shape of the commit history.",
  },
  {
    step: "03",
    title: "Score against a real job",
    detail:
      "A job description is parsed into weighted requirements and matched against what the " +
      "repository actually demonstrates, under a versioned scoring policy you control.",
  },
  {
    step: "04",
    title: "Verify with a conversation",
    detail:
      "Interview questions are generated from this repository's own functions, findings and " +
      "history — not from a question bank — so understanding can be checked directly.",
  },
];

const CAPABILITIES = [
  {
    icon: FileSearch,
    title: "Repository intelligence",
    detail:
      "AST-level metrics across Python, JavaScript, TypeScript, Java, C and C++: complexity, " +
      "duplication, nesting, error handling, test coverage signals and documentation quality.",
  },
  {
    icon: GitBranch,
    title: "Engineering evolution",
    detail:
      "Commit history read as a development story — implementation, fixes, refactoring, tests, " +
      "documentation, deployment — because that sequence is what ownership looks like.",
  },
  {
    icon: Sparkles,
    title: "AI ownership analysis",
    detail:
      "A probabilistic estimate of AI assistance, with every signal named, every alternative " +
      "explanation stated, and a confidence attached. Never a verdict.",
  },
  {
    icon: Target,
    title: "Job matching",
    detail:
      "Requirements matched to dependency, import, language and structural evidence — not to " +
      "keywords in a résumé.",
  },
  {
    icon: ShieldCheck,
    title: "Security review",
    detail:
      "Credential detection with entropy gating and injection-pattern analysis. Detected secrets " +
      "are masked at the point of detection and never stored or displayed.",
  },
  {
    icon: MessagesSquare,
    title: "Technical verification",
    detail:
      "Repository-anchored interview questions, assessed across correctness, specificity, " +
      "repository consistency, depth and communication — with reviewer override on every answer.",
  },
];

const PRINCIPLES = [
  {
    icon: Scale,
    title: "AI use is not misconduct",
    detail:
      "RepoLens measures whether a candidate can demonstrate ownership and understanding, " +
      "regardless of the tools they used. The AI-utilization score rewards effective augmentation, " +
      "not abstinence.",
  },
  {
    icon: Lock,
    title: "No automated rejection",
    detail:
      "The strongest outcome the system produces is “verification required” — a request for a " +
      "conversation. There is no reject status, and the hiring decision belongs to a human.",
  },
  {
    icon: Boxes,
    title: "Every score is checkable",
    detail:
      "Scores are deterministic and traceable to evidence with file and line references. Analyzers " +
      "that fail report a dimension as unavailable rather than guessing a number.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
              <FileSearch className="size-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight">RepoLens</span>
          </Link>
          <nav className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/login">Sign in</Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="/register">Get started</Link>
            </Button>
          </nav>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-border">
        <div className="grid-backdrop absolute inset-0" aria-hidden />
        <div className="relative mx-auto max-w-4xl px-6 py-24 text-center sm:py-32">
          <Badge variant="outline" className="mb-6">
            <Sparkles className="size-3" />
            Evidence-backed engineering evaluation
          </Badge>
          <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            Know What a GitHub Profile Really Proves.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">
            Evaluate engineering ability, project relevance, code quality and AI-assisted
            development using evidence from real repositories.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button size="lg" asChild>
              <Link href="/register?role=student">
                <Github className="size-4" />
                Analyze GitHub
              </Link>
            </Button>
            <Button size="lg" variant="secondary" asChild>
              <Link href="/register?role=interviewer">
                For interview teams
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
          <p className="mt-8 text-xs text-muted-foreground">
            RepoLens does not decide hiring outcomes and never claims that code was written by an AI.
          </p>
        </div>
      </section>

      <section className="border-b border-border py-20" id="how-it-works">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="How it works"
            title="From a repository URL to a defensible conversation"
          />
          <ol className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map((item) => (
              <li key={item.step} className="panel p-5">
                <span className="font-mono text-xs text-primary">{item.step}</span>
                <h3 className="mt-3 text-sm font-semibold">{item.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-b border-border py-20">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="What it analyses"
            title="Nine scored dimensions, every one traceable to evidence"
          />
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map((capability) => (
              <div key={capability.title} className="panel p-5">
                <div className="mb-3 inline-flex rounded-md border border-border bg-surface-raised p-2">
                  <capability.icon className="size-4 text-primary" />
                </div>
                <h3 className="text-sm font-semibold">{capability.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{capability.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border py-20">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 lg:grid-cols-2">
          <div className="panel p-7">
            <Badge variant="info" className="mb-4">For students</Badge>
            <h3 className="text-xl font-semibold tracking-tight">See what a reviewer will see</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Connect GitHub and get the honest version of your profile: what each repository proves,
              where the evidence is thin, which roles your work already supports, and the specific
              changes that would move each score — with the expected gain calculated from the real
              weighting.
            </p>
            <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
              {[
                "Engineering score with the basis it was computed from",
                "Per-repository scores with file-level evidence",
                "Job readiness across roles, and what is missing for each",
                "Interview questions from your own code, to practise against",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
                  {item}
                </li>
              ))}
            </ul>
            <Button className="mt-6" asChild>
              <Link href="/register?role=student">
                Analyze my GitHub
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>

          <div className="panel p-7">
            <Badge variant="accent" className="mb-4">For interviewers</Badge>
            <h3 className="text-xl font-semibold tracking-tight">Decide with evidence, not impressions</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Define the role, set the weighting that matters to your team, and compare candidates on
              what their repositories actually demonstrate. Every score opens into the observations
              behind it, and every machine finding can be overridden with your reasoning recorded
              alongside it.
            </p>
            <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
              {[
                "Job descriptions parsed into weighted, editable requirements",
                "Versioned scoring policies — historic evaluations stay explainable",
                "Ownership and similarity signals with their limitations stated",
                "Generated verification questions anchored to real code",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" />
                  {item}
                </li>
              ))}
            </ul>
            <Button className="mt-6" variant="secondary" asChild>
              <Link href="/register?role=interviewer">
                Set up a hiring workspace
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="border-b border-border py-20" id="responsible-evaluation">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHeading
            eyebrow="Privacy & responsible evaluation"
            title="What this tool refuses to do"
          />
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {PRINCIPLES.map((principle) => (
              <div key={principle.title} className="panel p-5">
                <div className="mb-3 inline-flex rounded-md border border-border bg-surface-raised p-2">
                  <principle.icon className="size-4 text-accent" />
                </div>
                <h3 className="text-sm font-semibold">{principle.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{principle.detail}</p>
              </div>
            ))}
          </div>
          <div className="panel mt-6 p-5">
            <p className="text-xs leading-relaxed text-muted-foreground">
              RepoLens analyses only technical evidence. It does not infer or record protected or
              personal characteristics. Repository contents are processed to produce metrics and are
              not retained as source; detected credentials are masked at the point of detection and
              never stored. Candidates can disclose AI use voluntarily, and a disclosure that differs
              from the repository signals is treated as context to discuss, never as evidence of
              dishonesty.
            </p>
          </div>
        </div>
      </section>

      <footer className="py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 sm:flex-row">
          <p className="text-center text-xs text-muted-foreground sm:text-left">
            RepoLens does not try to determine whether a candidate used AI. It determines whether the
            candidate demonstrates real engineering ability, ownership, relevance and understanding.
          </p>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <Link href="/login" className="hover:text-foreground">Sign in</Link>
            <Link href="/register" className="hover:text-foreground">Register</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-medium uppercase tracking-wide text-primary">{eyebrow}</p>
      <h2 className="mt-3 text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
    </div>
  );
}
