"use client";

import { Briefcase, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Label, Textarea } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { relativeTime, titleCase } from "@/lib/utils";

export default function JobsPage() {
  const jobs = useAsync(() => api.jobs.list({ limit: "100" }), []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Jobs</CardTitle>
            <CardDescription>
              A description is parsed into weighted requirements that evaluations are matched against.
            </CardDescription>
          </div>
          <NewJobDialog onCreated={jobs.reload} />
        </CardHeader>
        <CardContent>
          {jobs.loading ? (
            <DashboardSkeleton />
          ) : (jobs.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No jobs yet"
              description="Paste a real job description. RepoLens extracts the skills, decides which are required, and assigns each an importance weight you can edit."
              action={<NewJobDialog onCreated={jobs.reload} />}
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {jobs.data?.items.map((job) => (
                <Link key={job.id} href={`/interviewer/jobs/${job.id}`} className="panel-raised p-4 transition-colors hover:bg-muted/40">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{job.title}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {titleCase(job.experience_level)} · {titleCase(job.domain)} ·{" "}
                        {relativeTime(job.created_at)}
                      </p>
                    </div>
                    <Badge variant={job.is_open ? "success" : "default"}>
                      {job.is_open ? "open" : "closed"}
                    </Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1">
                    {job.requirements
                      .filter((requirement) => requirement.required)
                      .slice(0, 6)
                      .map((requirement) => (
                        <Badge key={requirement.skill} variant="outline" className="text-[10px]">
                          {requirement.label}
                        </Badge>
                      ))}
                    {job.requirements.filter((requirement) => requirement.required).length > 6 ? (
                      <Badge variant="default" className="text-[10px]">
                        +{job.requirements.filter((requirement) => requirement.required).length - 6}
                      </Badge>
                    ) : null}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NewJobDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [preview, setPreview] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  const [parsing, setParsing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const parse = async () => {
    if (description.trim().length < 10) return;
    setParsing(true);
    setError(null);
    try {
      setPreview(await api.jobs.parse({ title, description }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not parse the description.");
    } finally {
      setParsing(false);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.jobs.create({ title, description, is_public: false });
      setOpen(false);
      setTitle("");
      setDescription("");
      setPreview(null);
      onCreated();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the job.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          New job
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>Create a job</DialogTitle>
            <DialogDescription>
              Paste the real description. Parsing happens locally and deterministically — no model is
              required.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            {error ? <Alert tone="danger">{error}</Alert> : null}
            <div className="space-y-1.5">
              <Label htmlFor="title">Job title</Label>
              <Input
                id="title"
                required
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="AI/ML Engineering Intern"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                required
                rows={10}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                onBlur={parse}
                placeholder={
                  "Responsibilities:\n- ...\n\nRequirements:\n- Strong Python\n- PyTorch\n\nNice to have:\n- Docker"
                }
                className="font-mono text-xs"
              />
              <p className="text-[11px] text-muted-foreground">
                Headings such as “Requirements:” and “Nice to have:” decide which skills are treated
                as required.
              </p>
            </div>

            <Button type="button" variant="secondary" size="sm" onClick={parse} loading={parsing}>
              <Sparkles className="size-3.5" />
              Preview extracted requirements
            </Button>

            {preview ? (
              <div className="space-y-3 rounded-md border border-border bg-surface p-3">
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>Level: {titleCase(preview.experience_level)}</span>
                  <span>Domain: {titleCase(preview.domain)}</span>
                  {preview.min_years_experience ? (
                    <span>{preview.min_years_experience}+ years</span>
                  ) : null}
                </div>
                <div className="space-y-1">
                  {preview.requirements.slice(0, 14).map((requirement: any) => (
                    <div key={requirement.skill} className="flex items-center justify-between gap-3 text-xs">
                      <span className="flex items-center gap-2">
                        <Badge variant={requirement.required ? "success" : "default"} className="text-[10px]">
                          {requirement.required ? "required" : "preferred"}
                        </Badge>
                        {requirement.label}
                        {requirement.source === "implied" ? (
                          <span className="text-[10px] text-muted-foreground">(implied)</span>
                        ) : null}
                      </span>
                      <span className="tabular-nums text-muted-foreground">
                        {(requirement.importance * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
                {preview.notes?.length ? (
                  <Alert tone="warning">{preview.notes[0]}</Alert>
                ) : null}
              </div>
            ) : null}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Create job</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
