"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import { StatTile } from "@/components/score-card";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function AdminHealthPage() {
  const { data, loading, error, reload } = useAsync(() => api.admin.health(), []);

  if (loading) return <DashboardSkeleton />;
  if (error) return <Alert tone="danger" title="Could not load health">{error}</Alert>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      {data.configuration_problems?.length > 0 ? (
        <Alert tone="danger" title="Configuration problems">
          <ul className="space-y-1">
            {data.configuration_problems.map((problem: string, index: number) => (
              <li key={index}>{problem}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Users" value={data.totals.users} />
        <StatTile label="Repositories" value={data.totals.repositories} />
        <StatTile label="Analyses" value={data.totals.analyses} />
        <StatTile label="Evaluations" value={data.totals.evaluations} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Dependencies</CardTitle>
            <CardDescription>
              Degraded paths are reported honestly rather than hidden — a fallback is never presented
              as the real thing.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <DependencyRow
              label="Database"
              ok={data.dependencies.database.ok}
              detail={data.dependencies.database.error ?? "PostgreSQL reachable"}
            />
            <DependencyRow
              label="Analysis queue"
              ok={Boolean(data.dependencies.queue.healthy)}
              detail={
                data.dependencies.queue.note ??
                `${data.dependencies.queue.backend} · ${data.dependencies.queue.workers ?? 0} worker(s) · ${data.dependencies.queue.queued ?? 0} queued`
              }
            />
            <DependencyRow
              label="Rate limiter"
              ok={data.dependencies.rate_limiter.backend === "redis"}
              detail={`backend: ${data.dependencies.rate_limiter.backend}`}
              warnOnly
            />
            <DependencyRow
              label="Vector store"
              ok={data.dependencies.vector_store.backend === "pgvector"}
              detail={
                data.dependencies.vector_store.backend === "pgvector"
                  ? "pgvector extension available"
                  : "pgvector not installed; cosine similarity is computed in Python (prototype scale)"
              }
              warnOnly
            />
            <DependencyRow
              label="GitHub OAuth"
              ok={data.dependencies.github_oauth.configured}
              detail={
                data.dependencies.github_oauth.configured
                  ? "client credentials configured"
                  : "not configured; public repositories can still be imported by name"
              }
              warnOnly
            />
            <DependencyRow
              label="LLM"
              ok={data.dependencies.llm.configured}
              detail={data.dependencies.llm.note ?? `model ${data.dependencies.llm.model}`}
              warnOnly
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity (last 24 hours)</CardTitle>
            <CardDescription>Analysis throughput and analyzer reliability.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <StatTile label="Jobs" value={data.activity_24h.analysis_jobs} />
              <StatTile label="Completed" value={data.activity_24h.completed} />
              <StatTile label="Failed" value={data.activity_24h.failed} />
              <StatTile
                label="Avg duration"
                value={data.activity_24h.avg_duration_seconds}
                suffix="s"
              />
            </div>
            {Object.keys(data.activity_24h.analyzer_failures ?? {}).length > 0 ? (
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Analyzer failures
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(data.activity_24h.analyzer_failures).map(([analyzer, count]) => (
                    <Badge key={analyzer} variant="warning">
                      {analyzer}: {String(count)}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No analyzer failures in this window.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Versions</CardTitle>
          <CardDescription>
            Recorded on every evaluation so historic results stay reproducible.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-3">
            {Object.entries(data.versions).map(([key, value]) => (
              <div key={key} className="rounded-md border border-border p-3">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {titleCase(key)}
                </dt>
                <dd className="mt-1 font-mono text-sm">{String(value)}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function DependencyRow({
  label,
  ok,
  detail,
  warnOnly = false,
}: {
  label: string;
  ok: boolean;
  detail: string;
  warnOnly?: boolean;
}) {
  const Icon = ok ? CheckCircle2 : warnOnly ? AlertTriangle : XCircle;
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3">
      <Icon
        className={`mt-0.5 size-4 shrink-0 ${ok ? "text-success" : warnOnly ? "text-warning" : "text-danger"}`}
      />
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs leading-relaxed text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}
