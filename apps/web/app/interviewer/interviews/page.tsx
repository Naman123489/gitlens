"use client";

import { ClipboardList, Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { formatScore, relativeTime, titleCase } from "@/lib/utils";

function InterviewsInner() {
  const params = useSearchParams();
  const evaluationParam = params.get("evaluation");

  const sessions = useAsync(() => api.interviews.list(), []);
  const evaluations = useAsync(() => api.evaluations.list({ limit: "100" }), []);
  const [evaluationId, setEvaluationId] = React.useState(evaluationParam ?? "");
  const [count, setCount] = React.useState("8");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const create = async () => {
    if (!evaluationId) return;
    setBusy(true);
    setError(null);
    try {
      const session = await api.interviews.create({
        evaluation_id: evaluationId,
        question_count: Number(count),
      });
      window.location.href = `/interviewer/interviews/${session.id}`;
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the session.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Start a verification session</CardTitle>
          <CardDescription>
            Questions are generated from the candidate&apos;s own functions, findings and commit history —
            not from a question bank.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          {error ? <Alert tone="danger" className="w-full">{error}</Alert> : null}
          <div className="min-w-[18rem] flex-1 space-y-1.5">
            <label htmlFor="evaluation" className="text-xs font-medium text-muted-foreground">
              Evaluation
            </label>
            <Select
              id="evaluation"
              value={evaluationId}
              onChange={(event) => setEvaluationId(event.target.value)}
            >
              <option value="">Select an evaluation</option>
              {(evaluations.data?.items ?? []).map((evaluation) => (
                <option key={evaluation.id} value={evaluation.id}>
                  {evaluation.id.slice(0, 8)} · overall {formatScore(evaluation.overall_score)} ·{" "}
                  {titleCase(evaluation.verification_status)}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-32 space-y-1.5">
            <label htmlFor="count" className="text-xs font-medium text-muted-foreground">
              Questions
            </label>
            <Select id="count" value={count} onChange={(event) => setCount(event.target.value)}>
              {["5", "8", "10", "12"].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </Select>
          </div>
          <Button onClick={create} loading={busy} disabled={!evaluationId}>
            <Plus className="size-4" />
            Generate session
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
          <CardDescription>
            A verification score measures how well a candidate explained their own repository. It is
            one input to ownership confidence and is never a hiring decision.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {sessions.loading ? (
            <DashboardSkeleton />
          ) : (sessions.data ?? []).length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="No verification sessions yet"
              description="Generate one from an evaluation to get repository-specific questions."
            />
          ) : (
            (sessions.data ?? []).map((session) => (
              <Link
                key={session.id}
                href={`/interviewer/interviews/${session.id}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5 transition-colors hover:bg-muted/40"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">{session.title}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {session.questions.length} questions · {session.answers.length} answered ·{" "}
                    {relativeTime(session.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {session.verification_score !== null ? (
                    <span className="text-sm font-semibold tabular-nums">
                      {formatScore(session.verification_score)}/100
                    </span>
                  ) : null}
                  <Badge variant={session.status === "COMPLETED" ? "success" : "info"}>
                    {titleCase(session.status)}
                  </Badge>
                </div>
              </Link>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function InterviewsPage() {
  return (
    <React.Suspense fallback={<DashboardSkeleton />}>
      <InterviewsInner />
    </React.Suspense>
  );
}
