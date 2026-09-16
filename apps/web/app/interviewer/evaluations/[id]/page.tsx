"use client";

import {
  ArrowLeft,
  Download,
  MessagesSquare,
  PencilLine,
  StickyNote,
} from "lucide-react";
import Link from "next/link";
import { use } from "react";
import * as React from "react";

import { CategoryBars, DnaRadar } from "@/components/charts";
import { EvidencePanel, LimitationsPanel } from "@/components/evidence-panel";
import { CategoryScoreRow, ScoreDial, StatTile } from "@/components/score-card";
import { AIClassificationBadge, VerificationBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import type { Evidence } from "@/lib/types";
import { cn, formatScore, relativeTime, titleCase } from "@/lib/utils";

export default function EvaluationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const evaluation = useAsync(() => api.evaluations.get(id), [id]);
  const evidence = useAsync(() => api.evaluations.evidence(id), [id]);
  const notes = useAsync(() => api.evaluations.notes(id), [id]);
  const overrides = useAsync(() => api.evaluations.overrides(id), [id]);
  const [category, setCategory] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);

  if (evaluation.loading) return <DashboardSkeleton />;
  if (evaluation.error) return <Alert tone="danger" title="Could not load evaluation">{evaluation.error}</Alert>;
  if (!evaluation.data) return null;

  const data = evaluation.data;
  const allEvidence = evidence.data ?? [];
  const shown = category ? allEvidence.filter((item) => item.category === category) : allEvidence;

  const downloadReport = async () => {
    const markdown = await api.reports.markdown(id);
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `repolens-${id.slice(0, 8)}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/interviewer/evaluations">
            <ArrowLeft className="size-4" />
            All evaluations
          </Link>
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={downloadReport}>
            <Download className="size-4" />
            Export report
          </Button>
          <Button size="sm" asChild>
            <Link href={`/interviewer/interviews?evaluation=${id}`}>
              <MessagesSquare className="size-4" />
              Verify with questions
            </Link>
          </Button>
        </div>
      </div>

      {message ? <Alert tone="success">{message}</Alert> : null}

      {data.verification_status !== "CLEAR" ? (
        <Alert
          tone={data.verification_status === "VERIFICATION_REQUIRED" ? "warning" : "info"}
          title={
            data.verification_status === "VERIFICATION_REQUIRED"
              ? "Verification required"
              : titleCase(data.verification_status)
          }
        >
          <ul className="space-y-1">
            {data.verification_reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] italic">
            RepoLens never recommends rejecting a candidate. This flags what to ask about.
          </p>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[auto,1fr]">
        <Card className="flex flex-col items-center justify-center p-6 lg:w-56">
          <ScoreDial value={data.overall_score} label="Overall score" size={128} />
          <div className="mt-3 text-center">
            <VerificationBadge status={data.verification_status} />
            <p className="mt-2 text-[11px] text-muted-foreground">
              {Math.round(data.confidence * 100)}% confidence · policy {data.policy?.name} v
              {data.policy?.version}
            </p>
          </div>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Job match" value={data.job_match} suffix="%" footer={data.job?.title ?? "no role selected"} />
          <StatTile
            label="Ownership"
            value={data.ownership_confidence}
            suffix="%"
            help="Evidence that this candidate built and maintained the code. Low means thin evidence, not wrongdoing."
          />
          <StatTile
            label="AI utilization"
            value={data.ai_utilization}
            help="Whether AI appears to have been used productively while preserving ownership. It does not reward low AI usage."
          />
          <div className="panel flex flex-col justify-center gap-2 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">AI usage</p>
            <AIClassificationBadge classification={data.ai_classification} likelihood={data.ai_likelihood} />
            <p className="text-[11px] text-muted-foreground">
              estimate {formatScore(data.ai_likelihood)}/100
            </p>
          </div>

          <div className="sm:col-span-2 lg:col-span-4">
            <Card>
              <CardHeader>
                <CardTitle>{data.repository?.full_name}</CardTitle>
                <CardDescription>
                  {data.candidate?.full_name ? `${data.candidate.full_name} · ` : ""}
                  evaluated {relativeTime(data.created_at)} · analyzer{" "}
                  {String(data.versions.analyzer_version ?? "—")}
                </CardDescription>
              </CardHeader>
              {data.narrative?.text ? (
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">{data.narrative.text}</p>
                  <p className="mt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                    summary generated by {data.narrative.generated_by}
                  </p>
                </CardContent>
              ) : null}
            </Card>
          </div>
        </div>
      </div>

      <Tabs defaultValue="scores">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="scores">Scores &amp; evidence</TabsTrigger>
          <TabsTrigger value="relevance">Job relevance</TabsTrigger>
          <TabsTrigger value="resume">Résumé consistency</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
          <TabsTrigger value="review">Notes &amp; overrides</TabsTrigger>
          <TabsTrigger value="limits">Limitations</TabsTrigger>
        </TabsList>

        <TabsContent value="scores">
          <div className="grid gap-4 lg:grid-cols-[340px,1fr]">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle>Dimensions</CardTitle>
                <CardDescription>Select one to filter the evidence.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1">
                <button
                  type="button"
                  onClick={() => setCategory(null)}
                  className={cn(
                    "w-full rounded-md px-3 py-1.5 text-left text-xs transition-colors hover:bg-muted/50",
                    category === null && "bg-muted/60",
                  )}
                >
                  All evidence ({allEvidence.length})
                </button>
                {data.scores.map((score) => (
                  <CategoryScoreRow
                    key={score.category}
                    category={score.category}
                    score={score.score}
                    weight={score.weight}
                    confidence={score.confidence}
                    available={score.available}
                    unavailableReason={score.unavailable_reason}
                    active={category === score.category}
                    onClick={() => setCategory(score.category)}
                  />
                ))}
              </CardContent>
            </Card>

            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Score distribution</CardTitle>
                </CardHeader>
                <CardContent>
                  <CategoryBars data={data.scores} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <div>
                    <CardTitle>{category ? titleCase(category) : "All"} evidence</CardTitle>
                    <CardDescription>Expand a claim to see its observations.</CardDescription>
                  </div>
                  {category ? (
                    <OverrideDialog
                      evaluationId={data.id}
                      category={category}
                      currentScore={data.scores.find((score) => score.category === category)?.score ?? null}
                      onDone={() => {
                        evaluation.reload();
                        overrides.reload();
                        setMessage("Override recorded. The original value is preserved alongside it.");
                      }}
                    />
                  ) : null}
                </CardHeader>
                <CardContent>
                  <EvidencePanel evidence={shown as Evidence[]} />
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="relevance">
          <div className="grid gap-4 lg:grid-cols-[1fr,320px]">
            <Card>
              <CardHeader>
                <CardTitle>Skill evidence</CardTitle>
                <CardDescription>
                  Strength is derived from dependencies, imports, languages, paths and direct
                  observations — not from keywords.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Skill</TableHead>
                      <TableHead>Required</TableHead>
                      <TableHead className="text-right">Weight</TableHead>
                      <TableHead className="text-right">Evidence</TableHead>
                      <TableHead>Sources</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.skill_matches.length === 0 ? (
                      <TableEmpty colSpan={5}>
                        This evaluation was not scored against a job.
                      </TableEmpty>
                    ) : (
                      data.skill_matches.map((match) => (
                        <TableRow key={match.skill}>
                          <TableCell className="font-medium">{match.label}</TableCell>
                          <TableCell>
                            <Badge variant={match.required ? "success" : "default"} className="text-[10px]">
                              {match.required ? "required" : "preferred"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {(match.importance * 100).toFixed(1)}%
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right font-medium tabular-nums",
                              match.strength >= 0.6 ? "text-success" : match.strength >= 0.2 ? "text-warning" : "text-danger",
                            )}
                          >
                            {(match.strength * 100).toFixed(0)}%
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {match.sources.length === 0
                              ? "no evidence found"
                              : match.sources.map((source) => source.detail).join("; ")}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Engineering DNA</CardTitle>
              </CardHeader>
              <CardContent>
                <DnaRadar data={data.engineering_dna} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="resume">
          {data.resume_consistency ? (
            <Card>
              <CardHeader>
                <CardTitle>Résumé and repository evidence</CardTitle>
                <CardDescription>
                  {data.resume_consistency.supported} supported,{" "}
                  {data.resume_consistency.partially_supported} partially supported,{" "}
                  {data.resume_consistency.verification_recommended} recommended for verification.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Claim</TableHead>
                      <TableHead>Stated level</TableHead>
                      <TableHead className="text-right">Evidence</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.resume_consistency.items.map((item) => (
                      <TableRow key={item.skill}>
                        <TableCell className="font-medium">{item.label}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {item.claimed_level ?? "unspecified"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {(item.observed_evidence * 100).toFixed(0)}%
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              item.status === "supported"
                                ? "success"
                                : item.status === "partially_supported"
                                  ? "info"
                                  : "warning"
                            }
                          >
                            {titleCase(item.status)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {data.resume_consistency.unclaimed_strengths.length > 0 ? (
                  <div>
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      Evidenced but not claimed
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {data.resume_consistency.unclaimed_strengths.map((item) => (
                        <Badge key={item.skill} variant="info">{item.label}</Badge>
                      ))}
                    </div>
                  </div>
                ) : null}
                <Alert tone="info">{data.resume_consistency.limitation}</Alert>
              </CardContent>
            </Card>
          ) : (
            <Alert tone="info" title="No résumé on file">
              Upload a résumé on the candidate&apos;s profile to compare claimed skills with repository
              evidence.
            </Alert>
          )}
        </TabsContent>

        <TabsContent value="recommendations">
          <Card>
            <CardHeader>
              <CardTitle>Development recommendations</CardTitle>
              <CardDescription>
                Generated from this evaluation&apos;s own evidence. Expected gain is computed from the
                policy weights.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.recommendations.length === 0 ? (
                <p className="text-xs text-muted-foreground">No recommendations were generated.</p>
              ) : (
                data.recommendations.map((recommendation, index) => (
                  <div key={index} className="rounded-md border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{recommendation.title}</p>
                      <Badge variant="outline">{titleCase(recommendation.category)}</Badge>
                      {recommendation.expected_gain ? (
                        <Badge variant="success">+{recommendation.expected_gain.toFixed(1)}</Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {recommendation.detail}
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="review">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle>Reviewer notes</CardTitle>
                  <CardDescription>Private to your team unless shared explicitly.</CardDescription>
                </div>
                <NoteDialog evaluationId={data.id} onDone={notes.reload} />
              </CardHeader>
              <CardContent className="space-y-3">
                {(notes.data ?? []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No notes yet.</p>
                ) : (
                  (notes.data ?? []).map((note: any) => (
                    <div key={note.id} className="rounded-md border border-border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium">{note.author_name}</p>
                        <span className="text-[11px] text-muted-foreground">
                          {relativeTime(note.created_at)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm leading-relaxed">{note.body}</p>
                      {note.visible_to_candidate ? (
                        <Badge variant="info" className="mt-2 text-[10px]">shared with candidate</Badge>
                      ) : null}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Human overrides</CardTitle>
                <CardDescription>
                  The machine value is preserved alongside yours — an override annotates the record,
                  it does not rewrite it.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {(overrides.data ?? []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No overrides recorded.</p>
                ) : (
                  (overrides.data ?? []).map((override: any) => (
                    <div key={override.id} className="rounded-md border border-border p-3">
                      <p className="text-xs font-medium">
                        {override.author_name} · {override.target_type}:{override.target_key}
                      </p>
                      <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                        {JSON.stringify(override.original_value)} → {JSON.stringify(override.new_value)}
                      </p>
                      <p className="mt-1 text-xs">{override.rationale}</p>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="limits">
          <Card>
            <CardHeader>
              <CardTitle>What this evaluation could not establish</CardTitle>
              <CardDescription>
                Stated explicitly so a score is never read as more than it is.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <LimitationsPanel limitations={data.limitations} />
              {data.failures.length > 0 ? (
                <Alert tone="warning" title="Analyzer failures" className="mt-4">
                  <ul className="space-y-1">
                    {data.failures.map((failure, index) => (
                      <li key={index}>
                        <span className="font-mono text-[11px]">{failure.analyzer}</span>:{" "}
                        {failure.reason}
                      </li>
                    ))}
                  </ul>
                </Alert>
              ) : null}
              <div className="mt-4 rounded-md border border-border p-3">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Reproducibility
                </p>
                <dl className="mt-2 space-y-1">
                  {Object.entries(data.versions).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-3 text-xs">
                      <dt className="text-muted-foreground">{titleCase(key)}</dt>
                      <dd className="font-mono">{String(value ?? "—")}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function NoteDialog({ evaluationId, onDone }: { evaluationId: string; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [body, setBody] = React.useState("");
  const [shared, setShared] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.evaluations.addNote(evaluationId, { body, visible_to_candidate: shared });
      setOpen(false);
      setBody("");
      onDone();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="secondary">
          <StickyNote className="size-3.5" />
          Add note
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(32rem,94vw)]">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add a reviewer note</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={5}
              required
              placeholder="What you observed, and what you want to ask about."
            />
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={shared}
                onChange={(event) => setShared(event.target.checked)}
                className="size-3.5 rounded border-border"
              />
              Share this note with the candidate
            </label>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save note</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function OverrideDialog({
  evaluationId,
  category,
  currentScore,
  onDone,
}: {
  evaluationId: string;
  category: string;
  currentScore: number | null;
  onDone: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [score, setScore] = React.useState(String(currentScore ?? ""));
  const [rationale, setRationale] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.evaluations.addOverride(evaluationId, {
        target_type: "score",
        target_key: category,
        new_value: { score: Number(score) },
        rationale,
      });
      setOpen(false);
      onDone();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not record the override.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost">
          <PencilLine className="size-3.5" />
          Override
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(32rem,94vw)]">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Override the {titleCase(category)} score</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {error ? <Alert tone="danger">{error}</Alert> : null}
            <div className="space-y-1.5">
              <Label htmlFor="score">New score (0–100)</Label>
              <Input
                id="score"
                type="number"
                min={0}
                max={100}
                step={1}
                required
                value={score}
                onChange={(event) => setScore(event.target.value)}
              />
              <p className="text-[11px] text-muted-foreground">
                Machine value: {formatScore(currentScore)}. It is kept for the audit trail.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rationale">Rationale (required, min 10 characters)</Label>
              <Textarea
                id="rationale"
                required
                minLength={10}
                rows={4}
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                placeholder="Why the automatic score is wrong for this repository."
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Record override</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
