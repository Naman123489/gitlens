"use client";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function AnalyzersPage() {
  const { data, loading, error } = useAsync(() => api.admin.analyzers(), []);

  if (loading) return <DashboardSkeleton />;
  if (error) return <Alert tone="danger" title="Could not load analyzer configuration">{error}</Alert>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Analysis engine</CardTitle>
          <CardDescription>Version {data.analyzer_version}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Languages with full AST analysis
            </p>
            <div className="flex flex-wrap gap-1.5">
              {data.ast_languages.map((language: string) => (
                <Badge key={language} variant="info">{language}</Badge>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Other languages are counted by line and marked unparsed; their absence of functions is
              never read as “no functions”.
            </p>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Embeddings
            </p>
            <p className="text-xs text-muted-foreground">
              {data.embedding.dimensions} dimensions · store {data.embedding.backend} ·{" "}
              {data.embedding.kind}
            </p>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Resource limits
            </p>
            <dl className="grid gap-2 sm:grid-cols-3">
              {Object.entries(data.limits).map(([key, value]) => (
                <div key={key} className="rounded-md border border-border px-3 py-2">
                  <dt className="text-[11px] text-muted-foreground">{titleCase(key)}</dt>
                  <dd className="text-sm tabular-nums">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Security rules</CardTitle>
          <CardDescription>
            {data.security_rules.secret_patterns} credential patterns and{" "}
            {data.security_rules.code_patterns} code patterns. Each carries a confidence reflecting
            how often it is a true positive.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
                <TableHead>CWE</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.security_rules.rules.map((rule: any) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-medium">{rule.title}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {titleCase(rule.category)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        rule.severity === "critical" || rule.severity === "high"
                          ? "danger"
                          : rule.severity === "medium"
                            ? "warning"
                            : "default"
                      }
                    >
                      {rule.severity}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {Math.round(rule.confidence * 100)}%
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-muted-foreground">
                    {rule.cwe ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tutorial-derivation signals</CardTitle>
          <CardDescription>
            A curated, auditable set. There is no crawled corpus of tutorial repositories, so weak
            evidence yields “unknown” rather than “original”.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.tutorial_signals.map((signal: any) => (
            <div key={signal.id} className="rounded-md border border-border p-3">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-sm">{signal.label}</p>
                <span className="text-xs tabular-nums text-muted-foreground">
                  weight {signal.weight}
                </span>
              </div>
              {signal.note ? (
                <p className="mt-1 text-xs text-muted-foreground">{signal.note}</p>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
