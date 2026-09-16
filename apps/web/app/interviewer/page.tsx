"use client";

import { ArrowRight, Briefcase, FileSearch, Users } from "lucide-react";
import Link from "next/link";

import { StatTile } from "@/components/score-card";
import { VerificationBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { cn, formatScore, relativeTime, SCORE_BAND_TEXT, scoreBand } from "@/lib/utils";

export default function InterviewerOverviewPage() {
  const candidates = useAsync(() => api.candidates.list({ limit: "100" }), []);
  const jobs = useAsync(() => api.jobs.list({ limit: "50" }), []);
  const evaluations = useAsync(() => api.evaluations.list({ limit: "50" }), []);

  if (candidates.loading || jobs.loading || evaluations.loading) return <DashboardSkeleton />;

  const items = evaluations.data?.items ?? [];
  const needsVerification = items.filter((item) => item.verification_status === "VERIFICATION_REQUIRED");
  const scored = items.filter((item) => item.overall_score !== null);
  const average =
    scored.length > 0
      ? scored.reduce((total, item) => total + (item.overall_score ?? 0), 0) / scored.length
      : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Candidates" value={candidates.data?.total ?? 0} />
        <StatTile label="Open jobs" value={(jobs.data?.items ?? []).filter((job) => job.is_open).length} />
        <StatTile label="Evaluations" value={evaluations.data?.total ?? 0} />
        <StatTile
          label="Average score"
          value={average}
          footer={`${scored.length} scored evaluation${scored.length === 1 ? "" : "s"}`}
        />
      </div>

      {needsVerification.length > 0 ? (
        <Alert tone="warning" title={`${needsVerification.length} evaluation(s) need verification`}>
          These are requests for a conversation, not rejections. Each one lists exactly what could not
          be established from the repository alone.
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <QuickAction
          icon={Users}
          title="Candidates"
          detail="Add candidates, attach their repositories and compare their evidence."
          href="/interviewer/candidates"
        />
        <QuickAction
          icon={Briefcase}
          title="Jobs"
          detail="Paste a job description; it is parsed into weighted, editable requirements."
          href="/interviewer/jobs"
        />
        <QuickAction
          icon={FileSearch}
          title="Evaluations"
          detail="Score repositories against a role under a versioned policy."
          href="/interviewer/evaluations"
        />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Recent evaluations</CardTitle>
            <CardDescription>Ranked by overall score under the policy each one used.</CardDescription>
          </div>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/interviewer/evaluations">
              All evaluations
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Evaluation</TableHead>
                <TableHead className="text-right">Overall</TableHead>
                <TableHead className="text-right">Job match</TableHead>
                <TableHead className="text-right">Ownership</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableEmpty colSpan={6}>
                  No evaluations yet. Add a candidate and evaluate one of their repositories.
                </TableEmpty>
              ) : (
                items.slice(0, 8).map((evaluation) => (
                  <TableRow key={evaluation.id}>
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
                    <TableCell><VerificationBadge status={evaluation.verification_status} /></TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(evaluation.created_at)}
                    </TableCell>
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

function QuickAction({
  icon: Icon,
  title,
  detail,
  href,
}: {
  icon: typeof Users;
  title: string;
  detail: string;
  href: string;
}) {
  return (
    <Link href={href} className="panel group p-5 transition-colors hover:bg-surface-raised">
      <div className="mb-3 inline-flex rounded-md border border-border bg-surface-raised p-2">
        <Icon className="size-4 text-primary" />
      </div>
      <p className="flex items-center gap-1 text-sm font-semibold">
        {title}
        <ArrowRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
      </p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
    </Link>
  );
}
