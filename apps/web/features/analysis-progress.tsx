"use client";

import { AlertTriangle, Check, Loader2, Circle } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { AnalysisJob } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Live per-stage progress for a running analysis. */
export function AnalysisProgress({ job }: { job: AnalysisJob }) {
  const finished = job.status === "COMPLETED" || job.status === "FAILED" || job.status === "CANCELLED";

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            {job.status === "RUNNING" || job.status === "QUEUED" ? (
              <Loader2 className="size-4 animate-spin text-primary" />
            ) : null}
            Analysis {job.status.toLowerCase()}
          </CardTitle>
          <CardDescription>
            {job.current_stage ?? (job.status === "QUEUED" ? "Waiting for a worker" : "—")}
            {job.duration_seconds ? ` · ${job.duration_seconds.toFixed(1)}s` : ""}
          </CardDescription>
        </div>
        <Badge
          variant={
            job.status === "COMPLETED" ? "success" : job.status === "FAILED" ? "danger" : "info"
          }
        >
          {Math.round(job.progress * 100)}%
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={job.progress * 100} label="Analysis progress" />

        {job.error ? (
          <Alert tone={job.status === "FAILED" ? "danger" : "warning"} title={job.status === "FAILED" ? "Analysis failed" : "Waiting"}>
            {job.error}
          </Alert>
        ) : null}

        <ol className="grid gap-1.5 sm:grid-cols-2">
          {job.stages.map((stage) => {
            const Icon =
              stage.status === "completed" ? Check : stage.status === "running" ? Loader2 : Circle;
            return (
              <li
                key={stage.key}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs",
                  stage.status === "running" && "bg-muted/60",
                )}
              >
                <Icon
                  className={cn(
                    "size-3.5 shrink-0",
                    stage.status === "completed"
                      ? "text-success"
                      : stage.status === "running"
                        ? "animate-spin text-primary"
                        : "text-muted-foreground/40",
                  )}
                />
                <span className={stage.status === "pending" ? "text-muted-foreground" : ""}>
                  {stage.label}
                </span>
              </li>
            );
          })}
        </ol>

        {finished && job.status === "COMPLETED" ? (
          <p className="text-xs text-muted-foreground">
            Unchanged files are detected by content hash and reused on the next run.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** A failed analyzer is surfaced, never silently replaced with a number. */
export function AnalyzerFailures({
  failures,
}: {
  failures: { analyzer: string; category?: string | null; reason: string }[];
}) {
  if (failures.length === 0) return null;
  return (
    <Alert tone="warning" title={`${failures.length} analyzer(s) did not complete`}>
      <ul className="mt-1 space-y-1">
        {failures.map((failure, index) => (
          <li key={index}>
            <span className="font-mono text-[11px]">{failure.analyzer}</span>: {failure.reason}
          </li>
        ))}
      </ul>
      <p className="mt-2">
        The affected dimensions are reported as unavailable rather than estimated.
      </p>
    </Alert>
  );
}
