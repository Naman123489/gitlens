"use client";

import { ArrowRight, FolderGit2, Github, Sparkles } from "lucide-react";
import Link from "next/link";

import { DnaRadar } from "@/components/charts";
import { ScoreDial, StatTile } from "@/components/score-card";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { cn, formatScore, relativeTime, SCORE_BAND_TEXT, scoreBand, titleCase } from "@/lib/utils";

export default function StudentOverviewPage() {
  const { data, loading, error } = useAsync(() => api.student.dashboard(), []);

  if (loading) return <DashboardSkeleton />;
  if (error) return <Alert tone="danger" title="Could not load your profile">{error}</Alert>;
  if (!data) return null;

  if (data.empty_state) {
    return (
      <EmptyState
        icon={Github}
        title={data.empty_state.title}
        description={data.empty_state.detail}
        action={
          <Button asChild>
            <Link href="/student/repositories">
              Connect GitHub
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      />
    );
  }

  const analysed = data.repository_summaries.filter((repo) => repo.score !== null);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[auto,1fr]">
        <Card className="flex flex-col items-center justify-center p-6 lg:w-64">
          <ScoreDial value={data.engineering_score} label="GitHub engineering score" size={140} />
          <p className="mt-3 text-center text-[11px] leading-relaxed text-muted-foreground">
            {data.engineering_score_basis.method} Based on{" "}
            {data.engineering_score_basis.repositories_analysed} analysed repositor
            {data.engineering_score_basis.repositories_analysed === 1 ? "y" : "ies"}.
          </p>
        </Card>

        <div className="grid gap-4 sm:grid-cols-3">
          <StatTile
            label="Repositories"
            value={`${data.repositories.analysed}/${data.repositories.total}`}
            footer="analysed"
          />
          <StatTile
            label="Strongest dimension"
            value={data.strengths[0] ? titleCase(data.strengths[0].category) : "—"}
            footer={data.strengths[0] ? `${formatScore(data.strengths[0].score)}/100` : "Analyse a repository"}
          />
          <StatTile
            label="Weakest dimension"
            value={data.weaknesses[0] ? titleCase(data.weaknesses[0].category) : "—"}
            footer={data.weaknesses[0] ? `${formatScore(data.weaknesses[0].score)}/100` : "Nothing below 55"}
          />
          <div className="sm:col-span-3">
            <Card>
              <CardHeader>
                <CardTitle>Engineering DNA</CardTitle>
                <CardDescription>
                  Strength of evidence per dimension, taken from your strongest repository in each.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {Object.keys(data.engineering_dna).length > 0 ? (
                  <DnaRadar data={data.engineering_dna} />
                ) : (
                  <p className="py-8 text-center text-xs text-muted-foreground">
                    Run an evaluation to build your profile.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Repositories</CardTitle>
            <CardDescription>Each score links to the evidence behind it.</CardDescription>
          </div>
          <Button variant="secondary" size="sm" asChild>
            <Link href="/student/repositories">
              <FolderGit2 className="size-4" />
              Manage
            </Link>
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {data.repository_summaries.length === 0 ? (
            <EmptyState
              className="m-5"
              icon={Github}
              title="No repositories yet"
              description="Connect GitHub to begin your engineering profile."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Repository</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead className="text-right">Ownership</TableHead>
                  <TableHead>AI usage</TableHead>
                  <TableHead className="text-right">Analysed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.repository_summaries.map((repo) => (
                  <TableRow key={repo.id}>
                    <TableCell>
                      <Link href={`/student/repositories/${repo.id}`} className="font-medium hover:text-primary">
                        {repo.full_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{repo.primary_language ?? "—"}</TableCell>
                    <TableCell className={cn("text-right font-medium tabular-nums", SCORE_BAND_TEXT[scoreBand(repo.score)])}>
                      {formatScore(repo.score)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatScore(repo.ownership_confidence)}%
                    </TableCell>
                    <TableCell>
                      {repo.ai_classification ? (
                        <Badge variant="outline" className="text-[10px]">
                          {titleCase(repo.ai_classification)}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {repo.analysis_status === "COMPLETED"
                        ? relativeTime(repo.last_analyzed_at)
                        : titleCase(repo.analysis_status)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data.recommendations.length > 0 ? (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>What would move your score most</CardTitle>
              <CardDescription>
                Expected gain is calculated from the scoring weights, not estimated.
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/student/improve">
                Full plan
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.recommendations.slice(0, 4).map((recommendation, index) => (
              <div key={`${recommendation.title}-${index}`} className="flex items-start gap-3">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{recommendation.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                    {recommendation.detail}
                  </p>
                </div>
                {recommendation.expected_gain ? (
                  <Badge variant="success" className="shrink-0">
                    +{recommendation.expected_gain.toFixed(1)}
                  </Badge>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {analysed.length === 0 && data.repository_summaries.length > 0 ? (
        <Alert tone="info" title="Nothing analysed yet">
          Your repositories are imported but not analysed. Open one and run an analysis to see its
          scores.
        </Alert>
      ) : null}
    </div>
  );
}
