"use client";

import { ArrowLeft, FolderGit2, Play, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import * as React from "react";

import { DnaRadar } from "@/components/charts";
import { StatTile } from "@/components/score-card";
import { AIClassificationBadge, VerificationBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { cn, formatScore, relativeTime, SCORE_BAND_TEXT, scoreBand, titleCase } from "@/lib/utils";

export default function CandidateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const candidate = useAsync(() => api.candidates.get(id), [id]);
  const jobs = useAsync(() => api.jobs.list({ limit: "100" }), []);
  const disclosure = useAsync(() => api.candidates.disclosure(id), [id]);

  const [jobId, setJobId] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);

  if (candidate.loading) return <DashboardSkeleton />;
  if (candidate.error) return <Alert tone="danger" title="Could not load candidate">{candidate.error}</Alert>;
  if (!candidate.data) return null;

  const { candidate: profile, repositories, evaluations, summary } = candidate.data;

  const evaluate = async (repositoryId: string) => {
    setBusy(repositoryId);
    setMessage(null);
    try {
      const evaluation = await api.evaluations.create({
        repository_id: repositoryId,
        job_id: jobId || undefined,
        candidate_id: id,
      });
      setMessage({
        tone: "success",
        text: `Evaluation created — overall ${formatScore(evaluation.overall_score)}/100.`,
      });
      candidate.reload();
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not create the evaluation.",
      });
    } finally {
      setBusy(null);
    }
  };

  const analyse = async (repositoryId: string) => {
    setBusy(repositoryId);
    try {
      await api.repositories.analyze(repositoryId);
      setMessage({ tone: "success", text: "Analysis queued." });
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not queue the analysis.",
      });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link href="/interviewer/candidates">
          <ArrowLeft className="size-4" />
          All candidates
        </Link>
      </Button>

      {message ? <Alert tone={message.tone === "success" ? "success" : "danger"}>{message.text}</Alert> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr,320px]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{profile.full_name}</CardTitle>
            <CardDescription>
              {[profile.headline, profile.github_login ? `@${profile.github_login}` : null, profile.email]
                .filter(Boolean)
                .join(" · ") || "No additional details recorded."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-4">
            <StatTile label="Repositories" value={summary.repositories} />
            <StatTile label="Evaluations" value={summary.evaluations} />
            <StatTile label="Best score" value={summary.best_overall_score} />
            <StatTile
              label="Need verification"
              value={summary.needs_verification}
              help="Evaluations where a conversation is recommended. This is never a rejection."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Engineering DNA</CardTitle>
            <CardDescription>From their strongest evaluation.</CardDescription>
          </CardHeader>
          <CardContent>
            {Object.keys(summary.engineering_dna ?? {}).length > 0 ? (
              <DnaRadar data={summary.engineering_dna} />
            ) : (
              <p className="py-6 text-center text-xs text-muted-foreground">
                Evaluate a repository to build this profile.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {disclosure.data?.used_ai !== null && disclosure.data?.used_ai !== undefined ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-primary" />
              Candidate AI disclosure
            </CardTitle>
            <CardDescription>
              Written by the candidate. Stored separately from inferred signals.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">
              Declared AI use: <strong>{disclosure.data.used_ai ? "yes" : "no"}</strong>
            </p>
            {disclosure.data.purposes?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {disclosure.data.purposes.map((purpose: string) => (
                  <Badge key={purpose} variant="outline">{titleCase(purpose)}</Badge>
                ))}
              </div>
            ) : null}
            {disclosure.data.notes ? (
              <p className="text-xs leading-relaxed text-muted-foreground">{disclosure.data.notes}</p>
            ) : null}
            {disclosure.data.comparison ? (
              <Alert tone="info" title="Declared usage vs repository signals">
                <p>{disclosure.data.comparison.detail}</p>
                <p className="mt-2 text-[11px] italic">{disclosure.data.comparison.limitation}</p>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>Repositories</CardTitle>
            <CardDescription>Analyse first, then evaluate against a role.</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={jobId}
              onChange={(event) => setJobId(event.target.value)}
              className="h-8 w-56 text-xs"
              aria-label="Evaluate against job"
            >
              <option value="">No specific role</option>
              {(jobs.data?.items ?? []).map((job) => (
                <option key={job.id} value={job.id}>{job.title}</option>
              ))}
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {repositories.length === 0 ? (
            <EmptyState
              className="m-5"
              icon={FolderGit2}
              title="No repositories attached"
              description="The candidate can connect GitHub from their own account, or you can import a public repository on their behalf."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Repository</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Analysed</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {repositories.map((repo: any) => (
                  <TableRow key={repo.id}>
                    <TableCell>
                      <span className="font-medium">{repo.full_name}</span>
                      {repo.description ? (
                        <p className="max-w-md truncate text-xs text-muted-foreground">{repo.description}</p>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Badge variant={repo.analysis_status === "COMPLETED" ? "success" : "default"}>
                        {titleCase(repo.analysis_status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(repo.last_analyzed_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {repo.analysis_status === "COMPLETED" ? (
                          <Button size="sm" variant="secondary" loading={busy === repo.id} onClick={() => evaluate(repo.id)}>
                            Evaluate
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" loading={busy === repo.id} onClick={() => analyse(repo.id)}>
                            <Play className="size-3.5" />
                            Analyse
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Evaluations</CardTitle>
          <CardDescription>Each row opens the full evidence behind its scores.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Evaluation</TableHead>
                <TableHead className="text-right">Overall</TableHead>
                <TableHead className="text-right">Job match</TableHead>
                <TableHead className="text-right">Ownership</TableHead>
                <TableHead>AI usage</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {evaluations.length === 0 ? (
                <TableEmpty colSpan={6}>No evaluations yet.</TableEmpty>
              ) : (
                evaluations.map((evaluation: any) => (
                  <TableRow key={evaluation.id}>
                    <TableCell>
                      <Link
                        href={`/interviewer/evaluations/${evaluation.id}`}
                        className="font-mono text-xs hover:text-primary"
                      >
                        {evaluation.id.slice(0, 10)}
                      </Link>
                      <p className="text-[11px] text-muted-foreground">{relativeTime(evaluation.created_at)}</p>
                    </TableCell>
                    <TableCell className={cn("text-right font-medium tabular-nums", SCORE_BAND_TEXT[scoreBand(evaluation.overall_score)])}>
                      {formatScore(evaluation.overall_score)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatScore(evaluation.job_match)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatScore(evaluation.ownership_confidence)}%
                    </TableCell>
                    <TableCell>
                      <AIClassificationBadge
                        classification={evaluation.ai_classification}
                        likelihood={evaluation.ai_likelihood}
                      />
                    </TableCell>
                    <TableCell><VerificationBadge status={evaluation.verification_status} /></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
