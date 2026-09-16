"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const job = useAsync(() => api.jobs.get(id), [id]);
  const evaluations = useAsync(() => api.evaluations.list({ job_id: id, limit: "100" }), [id]);

  if (job.loading) return <DashboardSkeleton />;
  if (job.error) return <Alert tone="danger" title="Could not load job">{job.error}</Alert>;
  if (!job.data) return null;

  const data = job.data;
  const required = data.requirements.filter((requirement) => requirement.required);
  const preferred = data.requirements.filter((requirement) => !requirement.required);

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link href="/interviewer/jobs">
          <ArrowLeft className="size-4" />
          All jobs
        </Link>
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{data.title}</CardTitle>
          <CardDescription>
            {titleCase(data.experience_level)} · {titleCase(data.domain)}
            {data.min_years_experience ? ` · ${data.min_years_experience}+ years` : ""}
            {data.location ? ` · ${data.location}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data.responsibilities.length > 0 ? (
            <div>
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Responsibilities
              </p>
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {data.responsibilities.slice(0, 8).map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {data.parse_notes.length > 0 ? <Alert tone="warning">{data.parse_notes[0]}</Alert> : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <RequirementCard
          title="Required skills"
          description="Weights sum to 1 across all requirements and drive the job-relevance score."
          requirements={required}
        />
        <RequirementCard
          title="Preferred and implied"
          description="Implied skills are added automatically — asking for PyTorch implies Python."
          requirements={preferred}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Evaluations for this role</CardTitle>
          <CardDescription>
            {evaluations.data?.total ?? 0} evaluation(s) scored against this job.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {(evaluations.data?.items ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No evaluations yet. Open a candidate and evaluate one of their repositories against
              this role.
            </p>
          ) : (
            (evaluations.data?.items ?? []).map((evaluation) => (
              <Link
                key={evaluation.id}
                href={`/interviewer/evaluations/${evaluation.id}`}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-muted/40"
              >
                <span className="font-mono text-xs">{evaluation.id.slice(0, 10)}</span>
                <span className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>overall {evaluation.overall_score?.toFixed(0) ?? "—"}</span>
                  <span>match {evaluation.job_match?.toFixed(0) ?? "—"}%</span>
                  <Badge variant="outline">{titleCase(evaluation.verification_status)}</Badge>
                </span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RequirementCard({
  title,
  description,
  requirements,
}: {
  title: string;
  description: string;
  requirements: { skill: string; label: string; importance: number; source: string; matched_terms: string[] }[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {requirements.length === 0 ? (
          <p className="text-xs text-muted-foreground">None.</p>
        ) : (
          requirements.map((requirement) => (
            <div key={requirement.skill}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm">
                  {requirement.label}
                  {requirement.source !== "explicit" ? (
                    <span className="ml-1.5 text-[10px] text-muted-foreground">({requirement.source})</span>
                  ) : null}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {(requirement.importance * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={requirement.importance * 100 * 4} className="mt-1.5" />
              {requirement.matched_terms.length > 0 ? (
                <p className="mt-1 text-[10px] text-muted-foreground">
                  matched: {requirement.matched_terms.join(", ")}
                </p>
              ) : null}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
