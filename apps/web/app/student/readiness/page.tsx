"use client";

import { Target } from "lucide-react";
import Link from "next/link";

import { ReadinessBars } from "@/components/charts";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { SCORE_BAND_BG, scoreBand } from "@/lib/utils";

export default function ReadinessPage() {
  const { data, loading, error } = useAsync(() => api.student.readiness(), []);

  if (loading) return <DashboardSkeleton />;
  if (error) return <Alert tone="danger" title="Could not load readiness">{error}</Alert>;
  if (!data) return null;

  if (data.empty_state || data.roles.length === 0) {
    return (
      <EmptyState
        icon={Target}
        title={data.empty_state?.title ?? "Nothing to match yet"}
        description={
          data.empty_state?.detail ??
          "Analyse at least one repository to see how your work maps onto real roles."
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Job readiness</CardTitle>
          <CardDescription>
            {data.note ?? "Readiness uses the strongest evidence found across your repositories."}{" "}
            Based on {data.repositories} analysed repositor{data.repositories === 1 ? "y" : "ies"}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ReadinessBars data={data.roles.map((role) => ({ role: role.role, readiness: role.readiness }))} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {data.roles.map((role) => (
          <Card key={role.role}>
            <CardHeader>
              <div className="flex items-baseline justify-between gap-3">
                <CardTitle>{role.role}</CardTitle>
                <span className="text-lg font-semibold tabular-nums">{role.readiness.toFixed(0)}%</span>
              </div>
              <Progress
                value={role.readiness}
                indicatorClassName={SCORE_BAND_BG[scoreBand(role.readiness)]}
                label={`${role.role} readiness`}
              />
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Evidenced
                </p>
                {role.evidenced.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No required skill for this role is evidenced yet.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {role.evidenced.map((skill) => (
                      <Badge key={skill.skill} variant="success">
                        {skill.label} · {(skill.strength * 100).toFixed(0)}%
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {role.missing_required.length > 0 ? (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Missing required skills
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {role.missing_required.map((skill) => (
                      <Badge key={skill} variant="warning">{skill}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              {role.per_repository.length > 0 ? (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Best matching repositories
                  </p>
                  <ul className="space-y-1">
                    {role.per_repository.slice(0, 3).map((repo) => (
                      <li key={repo.repository_id} className="flex items-center justify-between gap-3 text-xs">
                        <Link
                          href={`/student/repositories/${repo.repository_id}`}
                          className="truncate hover:text-primary"
                        >
                          {repo.full_name}
                        </Link>
                        <span className="shrink-0 tabular-nums text-muted-foreground">
                          {repo.match?.toFixed(0) ?? "—"}%
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <Alert tone="info" title="What readiness measures">
        Readiness reflects evidence of the named technologies in your analysed repositories. It does
        not measure depth of expertise, and work in private repositories or at an employer will not
        appear here.
      </Alert>
    </div>
  );
}
