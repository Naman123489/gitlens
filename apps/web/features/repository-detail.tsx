"use client";

import {
  ExternalLink,
  GitCommitHorizontal,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import * as React from "react";

import { ActivityTimeline, CategoryBars } from "@/components/charts";
import { EvidencePanel, LimitationsPanel } from "@/components/evidence-panel";
import { CategoryScoreRow, ScoreDial, StatTile } from "@/components/score-card";
import { AIClassificationBadge, SeverityBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { AnalysisProgress, AnalyzerFailures } from "@/features/analysis-progress";
import { useAsync, usePolling } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import type { Analysis, Evidence, Repository, SecurityFinding } from "@/lib/types";
import { cn, formatScore, relativeTime, titleCase } from "@/lib/utils";

/**
 * The repository analysis view, shared by the student and interviewer portals.
 * Every score opens into the evidence that produced it.
 */
export function RepositoryDetail({ repositoryId }: { repositoryId: string }) {
  const [queuedJobId, setQueuedJobId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const repository = useAsync(() => api.repositories.get(repositoryId), [repositoryId]);
  const analysis = useAsync(
    () => api.repositories.analysis(repositoryId).catch(() => null),
    [repositoryId],
  );
  const jobs = useAsync(() => api.repositories.jobs(repositoryId), [repositoryId]);

  const activeJobId =
    queuedJobId ??
    jobs.data?.find((job) => job.status === "QUEUED" || job.status === "RUNNING")?.id ??
    null;

  const polled = usePolling(
    () => api.analysisJobs.get(activeJobId as string),
    (job) => ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status),
    2000,
    Boolean(activeJobId),
  );

  const activeJob = polled.data;
  const wasRunning = React.useRef(false);
  React.useEffect(() => {
    if (!activeJob) return;
    if (activeJob.status === "RUNNING" || activeJob.status === "QUEUED") {
      wasRunning.current = true;
    } else if (wasRunning.current) {
      wasRunning.current = false;
      setQueuedJobId(null);
      analysis.reload();
      repository.reload();
      jobs.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJob?.status]);

  const runAnalysis = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const job = await api.repositories.analyze(repositoryId, true);
      setQueuedJobId(job.id);
      jobs.reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "Could not queue the analysis.");
    } finally {
      setBusy(false);
    }
  };

  if (repository.loading) return <DashboardSkeleton />;
  if (repository.error) return <Alert tone="danger" title="Could not load repository">{repository.error}</Alert>;
  if (!repository.data) return null;

  const repo = repository.data;
  const data = analysis.data;

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-start justify-between gap-4 py-5">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">{repo.full_name}</h2>
              {repo.is_private ? <Badge variant="outline">private</Badge> : null}
              {repo.is_fork ? <Badge variant="outline">fork</Badge> : null}
              {repo.primary_language ? <Badge variant="info">{repo.primary_language}</Badge> : null}
            </div>
            {repo.description ? (
              <p className="max-w-2xl text-sm text-muted-foreground">{repo.description}</p>
            ) : null}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>{repo.stars} stars</span>
              <span>{repo.forks} forks</span>
              <span>{repo.size_kb} KB</span>
              <span>default branch {repo.default_branch}</span>
              <span>last analysed {relativeTime(repo.last_analyzed_at)}</span>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            {repo.html_url ? (
              <Button variant="ghost" size="sm" asChild>
                <a href={repo.html_url} target="_blank" rel="noreferrer noopener">
                  <ExternalLink className="size-4" />
                  GitHub
                </a>
              </Button>
            ) : null}
            <Button size="sm" onClick={runAnalysis} loading={busy} disabled={Boolean(activeJob && ["QUEUED", "RUNNING"].includes(activeJob.status))}>
              {data ? <RefreshCw className="size-4" /> : <Play className="size-4" />}
              {data ? "Re-analyse" : "Analyse"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {actionError ? <Alert tone="danger">{actionError}</Alert> : null}
      {activeJob && ["QUEUED", "RUNNING", "FAILED"].includes(activeJob.status) ? (
        <AnalysisProgress job={activeJob} />
      ) : null}

      {!data ? (
        analysis.loading ? (
          <DashboardSkeleton />
        ) : (
          <EmptyState
            icon={Play}
            title="Not analysed yet"
            description="Run an analysis to see scores, evidence and generated interview questions for this repository."
            action={<Button onClick={runAnalysis} loading={busy}>Analyse repository</Button>}
          />
        )
      ) : (
        <AnalysisView analysis={data} repository={repo} />
      )}
    </div>
  );
}

function AnalysisView({ analysis, repository }: { analysis: Analysis; repository: Repository }) {
  const evidence = (analysis.evidence ?? []) as unknown as Evidence[];
  const normalised = evidence.map((item) => ({
    ...item,
    evidence_id: (item as any).id ?? item.evidence_id,
    details: (item as any).evidence ?? item.details ?? [],
  })) as Evidence[];

  const results = analysis.results ?? {};
  const metrics = (name: string) => (results[name]?.metrics ?? {}) as Record<string, any>;
  const codeMetrics = metrics("code_metrics");
  const testing = metrics("testing");
  const documentation = metrics("documentation");
  const dependencies = metrics("dependencies");
  const architecture = metrics("architecture");
  const gitHistory = metrics("git_history");
  const ownership = metrics("ownership");
  const aiUsage = metrics("ai_usage");
  const utilization = metrics("ai_utilization");
  const similarity = metrics("similarity");

  const security = useAsync(() => api.repositories.security(repository.id), [repository.id]);

  const categories = Object.entries(analysis.category_scores).map(([category, value]) => ({
    category,
    score: value.score,
    confidence: value.confidence,
    available: value.score !== null,
    weight: 0,
  }));

  const byCategory = (category: string) => normalised.filter((item) => item.category === category);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[auto,1fr]">
        <Card className="flex flex-col items-center justify-center p-6 lg:w-56">
          <ScoreDial value={analysis.repository_score} label="Repository score" size={128} />
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            Mean of the available dimensions. A job-weighted score is produced when this repository
            is evaluated against a role.
          </p>
        </Card>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Ownership"
            value={analysis.ownership_confidence}
            suffix="%"
            help="Confidence that the evidence shows this candidate built and maintained the code. Low means thin evidence, not wrongdoing."
          />
          <StatTile
            label="AI utilization"
            value={analysis.ai_utilization}
            help="Whether AI appears to have been used productively while preserving ownership. It does not reward low AI usage."
            footer={utilization.classification}
          />
          <StatTile
            label="Test cases"
            value={testing.test_cases ?? null}
            footer={testing.frameworks?.length ? testing.frameworks.join(", ") : "no framework detected"}
          />
          <StatTile
            label="Commits"
            value={gitHistory.non_merge_commits ?? null}
            footer={
              gitHistory.active_days
                ? `${gitHistory.active_days} active days`
                : "no history available"
            }
          />
          <div className="sm:col-span-2 lg:col-span-4">
            <Card>
              <CardHeader>
                <CardTitle>Dimension scores</CardTitle>
                <CardDescription>
                  Each dimension is a weighted combination of measured sub-metrics.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <CategoryBars data={categories} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <AnalyzerFailures failures={analysis.failures} />

      <Tabs defaultValue="quality">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="quality">Code quality</TabsTrigger>
          <TabsTrigger value="testing">Testing</TabsTrigger>
          <TabsTrigger value="architecture">Architecture</TabsTrigger>
          <TabsTrigger value="docs">Documentation</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="git">Git evolution</TabsTrigger>
          <TabsTrigger value="ownership">Ownership &amp; AI</TabsTrigger>
          <TabsTrigger value="similarity">Similarity</TabsTrigger>
        </TabsList>

        <TabsContent value="quality">
          <DimensionPanel
            title="Code quality"
            score={analysis.category_scores.technical_quality?.score ?? null}
            metrics={[
              ["Functions", codeMetrics.function_count],
              ["Average complexity", codeMetrics.avg_complexity],
              ["Max complexity", codeMetrics.max_complexity],
              ["Average function length", codeMetrics.avg_function_lines],
              ["Max nesting", codeMetrics.max_nesting],
              ["Duplication", codeMetrics.duplication_ratio !== undefined ? `${(codeMetrics.duplication_ratio * 100).toFixed(1)}%` : undefined],
              ["Comment ratio", codeMetrics.comment_ratio !== undefined ? `${(codeMetrics.comment_ratio * 100).toFixed(1)}%` : undefined],
              ["Documented functions", codeMetrics.documented_function_ratio !== undefined ? `${(codeMetrics.documented_function_ratio * 100).toFixed(0)}%` : undefined],
            ]}
            subScores={codeMetrics.sub_scores}
            subWeights={codeMetrics.weights}
            evidence={byCategory("technical_quality")}
          />
        </TabsContent>

        <TabsContent value="testing">
          <DimensionPanel
            title="Testing"
            score={analysis.category_scores.testing?.score ?? null}
            metrics={[
              ["Test files", testing.test_files],
              ["Test cases", testing.test_cases],
              ["Test-to-source ratio", testing.test_to_source_ratio],
              ["Unit tests", testing.has_unit_tests ? "yes" : "no"],
              ["Integration tests", testing.has_integration_tests ? "yes" : "no"],
              ["End-to-end tests", testing.has_e2e_tests ? "yes" : "no"],
              ["CI runs tests", testing.ci_runs_tests ? "yes" : "no"],
              ["Coverage configured", testing.coverage_tracking_configured ? "yes" : "no"],
            ]}
            subScores={testing.sub_scores}
            subWeights={testing.weights}
            evidence={byCategory("testing")}
          />
        </TabsContent>

        <TabsContent value="architecture">
          <DimensionPanel
            title="Architecture"
            score={analysis.category_scores.architecture?.score ?? null}
            metrics={[
              ["Source files", architecture.source_files],
              ["Directories", architecture.directories],
              ["Layers detected", (architecture.layers_detected ?? []).map(titleCase).join(", ") || "none"],
              ["Frameworks", (architecture.frameworks ?? []).join(", ") || "none detected"],
              ["Internal imports per file", architecture.avg_internal_imports_per_file],
              ["Import cycles", (architecture.import_cycles ?? []).length],
              ["Dependencies", dependencies.unique_dependencies],
              ["Lock file", (dependencies.lock_files ?? []).length ? "committed" : "missing"],
            ]}
            subScores={architecture.sub_scores}
            subWeights={architecture.weights}
            evidence={byCategory("architecture")}
          />
        </TabsContent>

        <TabsContent value="docs">
          <DimensionPanel
            title="Documentation"
            score={analysis.category_scores.documentation?.score ?? null}
            metrics={[
              ["README", documentation.has_readme ? documentation.readme_path : "missing"],
              ["README words", documentation.readme_words],
              ["Supporting docs", documentation.doc_files],
              ["Placeholder text", documentation.placeholder_readme ? "present" : "none"],
            ]}
            evidence={byCategory("documentation")}
            extra={
              documentation.features ? (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(documentation.features as Record<string, boolean>).map(([key, present]) => (
                    <Badge key={key} variant={present ? "success" : "default"}>
                      {titleCase(key)}
                    </Badge>
                  ))}
                </div>
              ) : null
            }
          />
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle>Security findings</CardTitle>
              <CardDescription>
                Pattern-based static analysis. Detected credential values are masked at the point of
                detection and are never stored or displayed.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {security.loading ? (
                <p className="p-5 text-xs text-muted-foreground">Loading findings…</p>
              ) : (security.data?.length ?? 0) === 0 ? (
                <EmptyState
                  className="m-5"
                  icon={ShieldAlert}
                  title="No findings"
                  description="No hardcoded credentials or insecure patterns were detected in the analysed code."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Severity</TableHead>
                      <TableHead>Finding</TableHead>
                      <TableHead>Location</TableHead>
                      <TableHead className="text-right">Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(security.data ?? []).slice(0, 40).map((finding: SecurityFinding) => (
                      <TableRow key={finding.id}>
                        <TableCell><SeverityBadge severity={finding.severity} /></TableCell>
                        <TableCell>
                          <p className="text-sm">{finding.title}</p>
                          {finding.masked_value ? (
                            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                              {finding.masked_value}
                            </p>
                          ) : null}
                          {finding.remediation ? (
                            <p className="mt-1 text-xs text-muted-foreground">{finding.remediation}</p>
                          ) : null}
                          {finding.note ? (
                            <p className="mt-1 text-[11px] italic text-muted-foreground">{finding.note}</p>
                          ) : null}
                        </TableCell>
                        <TableCell className="font-mono text-[11px] text-muted-foreground">
                          {finding.file_path}:{finding.line}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {Math.round(finding.confidence * 100)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
          <div className="mt-4">
            <EvidencePanel evidence={byCategory("security")} />
          </div>
        </TabsContent>

        <TabsContent value="git">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Development timeline</CardTitle>
                <CardDescription>
                  Commit activity over the project&apos;s lifetime.
                  {gitHistory.evolution_score !== undefined
                    ? ` Engineering evolution score ${gitHistory.evolution_score}/100.`
                    : ""}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {gitHistory.timeline?.length ? (
                  <ActivityTimeline data={gitHistory.timeline} />
                ) : (
                  <EmptyState
                    icon={GitCommitHorizontal}
                    title="No commit history"
                    description="This repository was analysed without git metadata, so development-evolution signals are unavailable."
                  />
                )}
              </CardContent>
            </Card>
            <DimensionPanel
              title="Git engineering"
              score={analysis.category_scores.git_engineering?.score ?? null}
              metrics={[
                ["Commits", gitHistory.non_merge_commits],
                ["Contributors", gitHistory.contributors],
                ["Active days", gitHistory.active_days],
                ["Span (days)", gitHistory.span_days],
                ["Largest commit share", gitHistory.largest_commit_share !== undefined ? `${(gitHistory.largest_commit_share * 100).toFixed(0)}%` : undefined],
                ["Message quality", gitHistory.message_quality],
                ["Evolution phases", (gitHistory.evolution_phases ?? []).map(titleCase).join(", ") || "none"],
                ["Releases", (gitHistory.tags ?? []).length],
              ]}
              subScores={gitHistory.sub_scores}
            subWeights={gitHistory.weights}
              evidence={byCategory("git_engineering")}
            />
          </div>
        </TabsContent>

        <TabsContent value="ownership">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="size-4 text-primary" />
                  AI usage analysis
                </CardTitle>
                <CardDescription>
                  A probabilistic estimate built from weak individual signals. It is not a
                  determination that any code was AI-generated, and AI-assisted development is not
                  misconduct.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-4">
                  <StatTile label="Assistance likelihood" value={analysis.ai_likelihood} suffix="/100" />
                  <div className="space-y-1">
                    <AIClassificationBadge
                      classification={analysis.ai_classification}
                      likelihood={analysis.ai_likelihood}
                    />
                    <p className="max-w-lg text-xs text-muted-foreground">
                      {aiUsage.classification_description}
                    </p>
                    {aiUsage.confidence_band ? (
                      <p className="text-[11px] text-muted-foreground">
                        Estimate confidence: {aiUsage.confidence_band.replace("_", " ")}
                      </p>
                    ) : null}
                  </div>
                </div>

                {aiUsage.signals ? (
                  <div className="space-y-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Signals considered
                    </p>
                    {(aiUsage.signals as any[])
                      .slice()
                      .sort((a, b) => b.strength * b.weight - a.strength * a.weight)
                      .map((signal) => (
                        <div key={signal.id} className="rounded-md border border-border bg-surface px-3 py-2">
                          <div className="flex items-baseline justify-between gap-3">
                            <p className="text-sm">{signal.label}</p>
                            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                              strength {signal.strength.toFixed(2)} · weight {signal.weight}
                            </span>
                          </div>
                          <ul className="mt-1 space-y-0.5">
                            {(signal.observations ?? []).map((observation: string, index: number) => (
                              <li key={index} className="text-xs text-muted-foreground">
                                {observation}
                              </li>
                            ))}
                          </ul>
                          {signal.caveat ? (
                            <p className="mt-1 text-[11px] italic text-muted-foreground">
                              Alternative explanation: {signal.caveat}
                            </p>
                          ) : null}
                        </div>
                      ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <DimensionPanel
              title="Ownership confidence"
              score={analysis.ownership_confidence}
              scoreSuffix="%"
              evidence={byCategory("ownership")}
              extra={
                ownership.factors ? (
                  <div className="space-y-1.5">
                    {(ownership.factors as any[]).map((factor) => {
                      // A factor that could not be assessed is excluded from the
                      // score entirely. Rendering it as a 0% bar would read as a
                      // negative finding, which is exactly what the scoring
                      // engine refuses to do.
                      const unavailable = (
                        (ownership.unavailable_factors as string[]) ?? []
                      ).includes(factor.id);
                      return (
                        <div key={factor.id} className="flex items-center gap-3">
                          <span className="w-56 shrink-0 text-xs">{factor.label}</span>
                          {unavailable ? (
                            <span className="flex-1 text-[11px] italic text-muted-foreground">
                              not assessed — excluded from the score
                            </span>
                          ) : (
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                              <div
                                className={cn(
                                  "h-full rounded-full",
                                  factor.value >= 0.6
                                    ? "bg-success"
                                    : factor.value >= 0.3
                                      ? "bg-warning"
                                      : "bg-danger",
                                )}
                                style={{ width: `${Math.round(factor.value * 100)}%` }}
                              />
                            </div>
                          )}
                          <span className="w-10 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
                            {unavailable ? "—" : `${Math.round(factor.value * 100)}%`}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : null
              }
            />
          </div>
        </TabsContent>

        <TabsContent value="similarity">
          <Card>
            <CardHeader>
              <CardTitle>Similarity analysis</CardTitle>
              <CardDescription>
                Originality assessment: {titleCase(analysis.originality ?? "unknown")}. Similarity is
                computed against this deployment's own corpus; RepoLens does not search the public
                internet, so an absence of matches is not proof of originality.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <StatTile label="Chunks compared" value={similarity.chunks ?? null} />
                <StatTile
                  label="Internal duplicates"
                  value={
                    similarity.internal_duplicate_ratio !== undefined
                      ? Math.round(similarity.internal_duplicate_ratio * 100)
                      : null
                  }
                  suffix="%"
                />
                <StatTile
                  label="Corpus repositories"
                  value={similarity.corpus_repositories ?? null}
                  footer="available for comparison"
                />
              </div>

              {(similarity.tutorial_signals ?? []).length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Tutorial / scaffold signals
                  </p>
                  {(similarity.tutorial_signals as any[]).map((signal) => (
                    <div key={signal.id} className="rounded-md border border-border bg-surface px-3 py-2">
                      <p className="text-sm">{signal.label}</p>
                      {(signal.observations ?? []).map((observation: string, index: number) => (
                        <p key={index} className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                          {observation}
                        </p>
                      ))}
                      {signal.note ? (
                        <p className="mt-1 text-[11px] italic text-muted-foreground">{signal.note}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No scaffold or tutorial-derivation signals were found in the candidate-authored
                  code.
                </p>
              )}

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Function</TableHead>
                    <TableHead>Matches</TableHead>
                    <TableHead className="text-right">Similarity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(similarity.external_matches ?? []).length === 0 ? (
                    <TableEmpty colSpan={3}>
                      No close matches against other analysed repositories.
                    </TableEmpty>
                  ) : (
                    (similarity.external_matches as any[]).slice(0, 15).map((match, index) => (
                      <TableRow key={index}>
                        <TableCell className="font-mono text-xs">{match.symbol} · {match.file}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {match.matched_repository} · {match.matched_symbol}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{match.similarity}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Card>
        <CardHeader>
          <CardTitle>Limitations of this analysis</CardTitle>
          <CardDescription>What the analysis could not establish, stated explicitly.</CardDescription>
        </CardHeader>
        <CardContent>
          <LimitationsPanel limitations={analysis.limitations} />
        </CardContent>
      </Card>
    </div>
  );
}

function DimensionPanel({
  title,
  score,
  scoreSuffix = "",
  metrics,
  subScores,
  subWeights,
  evidence,
  extra,
}: {
  title: string;
  score: number | null;
  scoreSuffix?: string;
  metrics?: [string, unknown][];
  subScores?: Record<string, number>;
  /** Each sub-metric's weight *within this dimension*, from the analyzer. */
  subWeights?: Record<string, number>;
  evidence: Evidence[];
  extra?: React.ReactNode;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[320px,1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>Score {formatScore(score)}{scoreSuffix}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {metrics ? (
            <dl className="space-y-1.5">
              {metrics
                .filter(([, value]) => value !== undefined && value !== null && value !== "")
                .map(([label, value]) => (
                  <div key={label} className="flex items-baseline justify-between gap-3 text-xs">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="text-right font-medium tabular-nums">{String(value)}</dd>
                  </div>
                ))}
            </dl>
          ) : null}

          {subScores && Object.keys(subScores).length > 0 ? (
            <div className="space-y-2 border-t border-border pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Sub-metrics
              </p>
              {Object.entries(subScores).map(([key, value]) => (
                <CategoryScoreRow
                  key={key}
                  category={key}
                  score={value}
                  weight={subWeights?.[key]}
                  confidence={1}
                  available
                  showConfidence={false}
                />
              ))}
            </div>
          ) : null}

          {extra}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Why this score</CardTitle>
          <CardDescription>Expand any claim to see the observations behind it.</CardDescription>
        </CardHeader>
        <CardContent>
          <EvidencePanel evidence={evidence} />
        </CardContent>
      </Card>
    </div>
  );
}
