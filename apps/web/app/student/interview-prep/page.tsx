"use client";

import { MessagesSquare, Send } from "lucide-react";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import type { InterviewSession } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

export default function InterviewPrepPage() {
  const repositories = useAsync(() => api.repositories.list({ limit: 100 }), []);
  const [repositoryId, setRepositoryId] = React.useState("");
  const [session, setSession] = React.useState<InterviewSession | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const analysed = (repositories.data?.items ?? []).filter(
    (repo) => repo.analysis_status === "COMPLETED",
  );

  React.useEffect(() => {
    if (!repositoryId && analysed.length > 0) setRepositoryId(analysed[0].id);
  }, [analysed, repositoryId]);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setSession(
        await api.interviews.create({
          repository_id: repositoryId,
          title: "Practice session",
          question_count: 6,
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start a practice session.");
    } finally {
      setBusy(false);
    }
  };

  if (repositories.loading) return <DashboardSkeleton />;

  if (analysed.length === 0) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="Nothing to practise against yet"
        description="Analyse a repository first — questions are generated from your own functions, findings and commit history, not from a question bank."
      />
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Practise on your own code</CardTitle>
          <CardDescription>
            These are the questions an interviewer would be shown for this repository. Answering them
            here is private to you and is not recorded against any evaluation.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="min-w-[16rem] flex-1 space-y-1.5">
            <label htmlFor="repo" className="text-xs font-medium text-muted-foreground">
              Repository
            </label>
            <Select
              id="repo"
              value={repositoryId}
              onChange={(event) => setRepositoryId(event.target.value)}
            >
              {analysed.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.full_name}
                </option>
              ))}
            </Select>
          </div>
          <Button onClick={start} loading={busy} disabled={!repositoryId}>
            Generate questions
          </Button>
        </CardContent>
      </Card>

      {error ? <Alert tone="danger">{error}</Alert> : null}

      {session ? <PracticeSession session={session} /> : null}
    </div>
  );
}

function PracticeSession({ session }: { session: InterviewSession }) {
  return (
    <div className="space-y-4">
      {session.questions.map((question, index) => (
        <PracticeQuestion key={question.id} sessionId={session.id} question={question} index={index} />
      ))}
    </div>
  );
}

function PracticeQuestion({
  sessionId,
  question,
  index,
}: {
  sessionId: string;
  question: InterviewSession["questions"][number];
  index: number;
}) {
  const [answer, setAnswer] = React.useState("");
  const [result, setResult] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.interviews.answer(sessionId, { question_id: question.id, answer_text: answer }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not assess the answer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{titleCase(question.category)}</Badge>
          <Badge variant="default">{question.difficulty}</Badge>
          <span className="text-xs text-muted-foreground">Question {index + 1}</span>
        </div>
        <CardTitle className="mt-2 text-sm font-medium leading-relaxed">{question.question}</CardTitle>
        <CardDescription>{question.rationale}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          placeholder="Answer as you would out loud. Reference specific files and decisions."
          rows={4}
        />
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={submit} loading={busy} disabled={answer.trim().length < 5}>
            <Send className="size-3.5" />
            Assess my answer
          </Button>
          {question.expected_points.length > 0 ? (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none hover:text-foreground">
                What a strong answer covers
              </summary>
              <ul className="mt-2 list-inside list-disc space-y-0.5">
                {question.expected_points.map((point, pointIndex) => (
                  <li key={pointIndex}>{point}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>

        {error ? <Alert tone="danger">{error}</Alert> : null}

        {result ? (
          <div className="rounded-md border border-border bg-surface p-3">
            <div className="flex items-baseline justify-between">
              <p className="text-sm font-medium">Assessment: {result.score?.toFixed(0)}/100</p>
              <span className="text-[11px] text-muted-foreground">
                assessed by {result.assessed_by}
              </span>
            </div>
            <dl className="mt-2 space-y-1.5">
              {Object.entries(result.assessment?.dimensions ?? {}).map(([key, value]: [string, any]) => (
                <div key={key} className="text-xs">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-muted-foreground">{titleCase(key)}</dt>
                    <dd
                      className={cn(
                        "font-medium tabular-nums",
                        value.score >= 70 ? "text-success" : value.score >= 45 ? "text-warning" : "text-danger",
                      )}
                    >
                      {value.score?.toFixed(0)}
                    </dd>
                  </div>
                  <p className="text-[11px] text-muted-foreground">{value.detail}</p>
                </div>
              ))}
            </dl>
            {result.assessment?.limitation ? (
              <p className="mt-3 border-t border-border pt-2 text-[11px] italic text-muted-foreground">
                {result.assessment.limitation}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
