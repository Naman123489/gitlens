"use client";

import { ArrowLeft, CheckCircle2, Send } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import type { InterviewAnswer, InterviewQuestion } from "@/lib/types";
import { cn, formatScore, titleCase } from "@/lib/utils";

export default function InterviewSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const session = useAsync(() => api.interviews.get(id), [id]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  if (session.loading) return <DashboardSkeleton />;
  if (session.error) return <Alert tone="danger" title="Could not load session">{session.error}</Alert>;
  if (!session.data) return null;

  const data = session.data;
  const answersByQuestion = new Map(data.answers.map((answer) => [answer.question_id, answer]));

  const complete = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.interviews.complete(id);
      session.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not complete the session.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/interviewer/interviews">
            <ArrowLeft className="size-4" />
            All sessions
          </Link>
        </Button>
        {data.status === "OPEN" ? (
          <Button size="sm" onClick={complete} loading={busy} disabled={data.answers.length === 0}>
            <CheckCircle2 className="size-4" />
            Complete and score
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="danger">{error}</Alert> : null}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">{data.title}</CardTitle>
              <CardDescription>
                {data.questions.length} questions · {data.answers.length} answered
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              {data.verification_score !== null ? (
                <span className="text-2xl font-semibold tabular-nums">
                  {formatScore(data.verification_score)}
                  <span className="text-sm font-normal text-muted-foreground">/100</span>
                </span>
              ) : null}
              <Badge variant={data.status === "COMPLETED" ? "success" : "info"}>
                {titleCase(data.status)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        {data.summary ? (
          <CardContent>
            <p className="text-sm leading-relaxed text-muted-foreground">{data.summary}</p>
            {Object.keys(data.dimension_scores ?? {}).length > 0 ? (
              <dl className="mt-4 grid gap-2 sm:grid-cols-5">
                {Object.entries(data.dimension_scores).map(([key, value]) => (
                  <div key={key} className="rounded-md border border-border p-2">
                    <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {titleCase(key)}
                    </dt>
                    <dd className="mt-0.5 text-sm font-semibold tabular-nums">{value.toFixed(0)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </CardContent>
        ) : null}
      </Card>

      <div className="space-y-4">
        {data.questions.map((question, index) => (
          <QuestionCard
            key={question.id}
            sessionId={id}
            question={question}
            index={index}
            answer={answersByQuestion.get(question.id)}
            readOnly={data.status !== "OPEN"}
            onChanged={session.reload}
          />
        ))}
      </div>
    </div>
  );
}

function QuestionCard({
  sessionId,
  question,
  index,
  answer,
  readOnly,
  onChanged,
}: {
  sessionId: string;
  question: InterviewQuestion;
  index: number;
  answer?: InterviewAnswer;
  readOnly: boolean;
  onChanged: () => void;
}) {
  const [text, setText] = React.useState(answer?.answer_text ?? "");
  const [reviewerScore, setReviewerScore] = React.useState(
    answer?.reviewer_score !== null && answer?.reviewer_score !== undefined
      ? String(answer.reviewer_score)
      : "",
  );
  const [comment, setComment] = React.useState(answer?.reviewer_comment ?? "");
  const [busy, setBusy] = React.useState(false);

  const submitAnswer = async () => {
    setBusy(true);
    try {
      await api.interviews.answer(sessionId, { question_id: question.id, answer_text: text });
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const submitReview = async () => {
    if (!answer) return;
    setBusy(true);
    try {
      await api.interviews.review(sessionId, answer.id, {
        reviewer_score: Number(reviewerScore),
        reviewer_comment: comment,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{titleCase(question.category)}</Badge>
          <Badge>{question.difficulty}</Badge>
          <span className="text-xs text-muted-foreground">Question {index + 1}</span>
          {question.generated_by === "fallback" ? (
            <Badge variant="warning" className="text-[10px]">generic fallback</Badge>
          ) : null}
        </div>
        <CardTitle className="mt-2 text-sm font-medium leading-relaxed">{question.question}</CardTitle>
        <CardDescription>{question.rationale}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {question.anchors.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {question.anchors.map((anchor, anchorIndex) => (
              <Badge key={anchorIndex} variant="default" className="font-mono text-[10px]">
                {anchor.file}
                {anchor.line ? `:${anchor.line}` : ""}
              </Badge>
            ))}
          </div>
        ) : null}

        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={4}
          disabled={readOnly}
          placeholder="Record the candidate's answer."
        />
        {!readOnly ? (
          <Button size="sm" onClick={submitAnswer} loading={busy} disabled={text.trim().length < 5}>
            <Send className="size-3.5" />
            {answer ? "Update and re-assess" : "Save and assess"}
          </Button>
        ) : null}

        {answer ? (
          <div className="rounded-md border border-border bg-surface p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-medium">
                Automatic assessment: {formatScore(answer.score)}/100
              </p>
              <span className="text-[11px] text-muted-foreground">
                assessed by {answer.assessed_by}
              </span>
            </div>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              {Object.entries(answer.assessment?.dimensions ?? {}).map(([key, value]) => (
                <div key={key} className="text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-muted-foreground">{titleCase(key)}</dt>
                    <dd
                      className={cn(
                        "font-medium tabular-nums",
                        value.score >= 70 ? "text-success" : value.score >= 45 ? "text-warning" : "text-danger",
                      )}
                    >
                      {value.score.toFixed(0)}
                    </dd>
                  </div>
                  <p className="text-[11px] text-muted-foreground">{value.detail}</p>
                </div>
              ))}
            </dl>
            {answer.assessment?.limitation ? (
              <p className="mt-3 border-t border-border pt-2 text-[11px] italic text-muted-foreground">
                {answer.assessment.limitation}
              </p>
            ) : null}

            {!readOnly ? (
              <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-border pt-3">
                <div className="w-28 space-y-1">
                  <Label htmlFor={`score-${question.id}`}>Your score</Label>
                  <Input
                    id={`score-${question.id}`}
                    type="number"
                    min={0}
                    max={100}
                    value={reviewerScore}
                    onChange={(event) => setReviewerScore(event.target.value)}
                  />
                </div>
                <div className="min-w-[14rem] flex-1 space-y-1">
                  <Label htmlFor={`comment-${question.id}`}>Comment</Label>
                  <Input
                    id={`comment-${question.id}`}
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    placeholder="Why you scored it this way"
                  />
                </div>
                <Button size="sm" variant="secondary" onClick={submitReview} loading={busy} disabled={!reviewerScore}>
                  Save my score
                </Button>
              </div>
            ) : answer.reviewer_score !== null ? (
              <p className="mt-3 border-t border-border pt-2 text-xs">
                Reviewer score: <strong>{answer.reviewer_score}</strong>
                {answer.reviewer_comment ? ` — ${answer.reviewer_comment}` : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
