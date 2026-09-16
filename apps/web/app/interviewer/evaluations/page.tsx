"use client";

import { FileSearch, GitCompare } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AIClassificationBadge, VerificationBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { cn, formatScore, relativeTime, SCORE_BAND_TEXT, scoreBand, titleCase } from "@/lib/utils";

const STATUSES = ["CLEAR", "REVIEW_RECOMMENDED", "VERIFICATION_REQUIRED", "ANALYSIS_INCOMPLETE"];

export default function EvaluationsPage() {
  const [jobId, setJobId] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [minScore, setMinScore] = React.useState("");
  const [selected, setSelected] = React.useState<string[]>([]);
  const [comparison, setComparison] = React.useState<any>(null);

  const jobs = useAsync(() => api.jobs.list({ limit: "100" }), []);
  const evaluations = useAsync(
    () =>
      api.evaluations.list({
        limit: "200",
        ...(jobId ? { job_id: jobId } : {}),
        ...(status ? { verification_status: status } : {}),
        ...(minScore ? { min_score: minScore } : {}),
      }),
    [jobId, status, minScore],
  );

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id].slice(-6),
    );

  const compare = async () => {
    setComparison(await api.evaluations.compare(selected));
  };

  const items = evaluations.data?.items ?? [];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-end justify-between gap-3">
          <div>
            <CardTitle>Evaluations</CardTitle>
            <CardDescription>
              Ranked by overall score. Scores are only comparable when the same policy version was
              used — the policy column shows which.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={jobId}
              onChange={(event) => setJobId(event.target.value)}
              className="h-8 w-44 text-xs"
              aria-label="Filter by job"
            >
              <option value="">All jobs</option>
              {(jobs.data?.items ?? []).map((job) => (
                <option key={job.id} value={job.id}>{job.title}</option>
              ))}
            </Select>
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="h-8 w-48 text-xs"
              aria-label="Filter by verification status"
            >
              <option value="">Any status</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>{titleCase(value)}</option>
              ))}
            </Select>
            <Input
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(event) => setMinScore(event.target.value)}
              placeholder="Min score"
              className="h-8 w-28 text-xs"
              aria-label="Minimum overall score"
            />
            <Button
              size="sm"
              variant="secondary"
              disabled={selected.length < 2}
              onClick={compare}
            >
              <GitCompare className="size-3.5" />
              Compare {selected.length > 0 ? `(${selected.length})` : ""}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {evaluations.loading ? (
            <DashboardSkeleton />
          ) : items.length === 0 ? (
            <EmptyState
              className="m-5"
              icon={FileSearch}
              title="No evaluations match"
              description="Evaluate a candidate's analysed repository against a role to populate this list."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Evaluation</TableHead>
                  <TableHead className="text-right">Overall</TableHead>
                  <TableHead className="text-right">Match</TableHead>
                  <TableHead className="text-right">Ownership</TableHead>
                  <TableHead>AI usage</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((evaluation) => (
                  <TableRow key={evaluation.id}>
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={selected.includes(evaluation.id)}
                        onChange={() => toggle(evaluation.id)}
                        className="size-3.5 rounded border-border"
                        aria-label={`Select evaluation ${evaluation.id.slice(0, 8)}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/interviewer/evaluations/${evaluation.id}`}
                        className="font-mono text-xs hover:text-primary"
                      >
                        {evaluation.id.slice(0, 10)}
                      </Link>
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
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(evaluation.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {comparison ? (
        <Card>
          <CardHeader>
            <CardTitle>Comparison</CardTitle>
            <CardDescription>{comparison.note}</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dimension</TableHead>
                  {comparison.evaluations.map((evaluation: any) => (
                    <TableHead key={evaluation.id} className="text-right">
                      {evaluation.candidate ?? evaluation.repository ?? evaluation.id.slice(0, 8)}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">Overall</TableCell>
                  {comparison.evaluations.map((evaluation: any) => (
                    <TableCell
                      key={evaluation.id}
                      className={cn("text-right font-semibold tabular-nums", SCORE_BAND_TEXT[scoreBand(evaluation.overall_score)])}
                    >
                      {formatScore(evaluation.overall_score)}
                    </TableCell>
                  ))}
                </TableRow>
                {comparison.categories.map((row: any) => (
                  <TableRow key={row.category}>
                    <TableCell>{titleCase(row.category)}</TableCell>
                    {comparison.evaluations.map((evaluation: any) => {
                      const value = row.values[evaluation.id];
                      return (
                        <TableCell
                          key={evaluation.id}
                          className={cn(
                            "text-right tabular-nums",
                            value?.available ? SCORE_BAND_TEXT[scoreBand(value.score)] : "text-muted-foreground",
                          )}
                          title={value?.unavailable_reason ?? undefined}
                        >
                          {value?.available ? formatScore(value.score) : "n/a"}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell className="text-xs text-muted-foreground">Policy version</TableCell>
                  {comparison.evaluations.map((evaluation: any) => (
                    <TableCell key={evaluation.id} className="text-right text-xs text-muted-foreground">
                      v{evaluation.policy ?? "?"}
                    </TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : selected.length >= 2 ? (
        <Alert tone="info">
          {selected.length} evaluations selected. Choose “Compare” to see them side by side.
        </Alert>
      ) : null}
    </div>
  );
}
