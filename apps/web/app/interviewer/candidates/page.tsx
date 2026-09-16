"use client";

import { Plus, Search, Users } from "lucide-react";
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
import { Input, Label } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

export default function CandidatesPage() {
  const [search, setSearch] = React.useState("");
  const candidates = useAsync(() => api.candidates.list({ limit: "200" }), []);

  const filtered = (candidates.data?.items ?? []).filter((candidate) =>
    `${candidate.full_name} ${candidate.email ?? ""} ${candidate.github_login ?? ""}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>Candidates</CardTitle>
            <CardDescription>
              Everyone in your workspace, with the evidence gathered so far.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search"
                className="h-8 w-44 pl-8 text-xs"
                aria-label="Search candidates"
              />
            </div>
            <NewCandidateDialog onCreated={candidates.reload} />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {candidates.loading ? (
            <DashboardSkeleton />
          ) : filtered.length === 0 ? (
            <EmptyState
              className="m-5"
              icon={Users}
              title="No candidates yet"
              description="Add a candidate, attach the repositories they want assessed, and evaluate those against a role."
              action={<NewCandidateDialog onCreated={candidates.reload} />}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>GitHub</TableHead>
                  <TableHead>Résumé</TableHead>
                  <TableHead>Disclosure</TableHead>
                  <TableHead className="text-right">Added</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((candidate) => (
                  <TableRow key={candidate.id}>
                    <TableCell>
                      <Link
                        href={`/interviewer/candidates/${candidate.id}`}
                        className="font-medium hover:text-primary"
                      >
                        {candidate.full_name}
                      </Link>
                      {candidate.headline ? (
                        <p className="text-xs text-muted-foreground">{candidate.headline}</p>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {candidate.github_login ?? "—"}
                    </TableCell>
                    <TableCell>
                      {candidate.has_resume ? (
                        <Badge variant="success">uploaded</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {candidate.has_disclosure ? (
                        <Badge variant="info">provided</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">not provided</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(candidate.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NewCandidateDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [githubLogin, setGithubLogin] = React.useState("");
  const [headline, setHeadline] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.candidates.create({
        full_name: fullName,
        email: email || undefined,
        github_login: githubLogin || undefined,
        headline: headline || undefined,
      });
      setOpen(false);
      setFullName("");
      setEmail("");
      setGithubLogin("");
      setHeadline("");
      onCreated();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not add the candidate.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          Add candidate
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(30rem,94vw)]">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add a candidate</DialogTitle>
            <DialogDescription>
              Only what is needed for technical evaluation. RepoLens does not record personal
              characteristics.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {error ? <Alert tone="danger">{error}</Alert> : null}
            <div className="space-y-1.5">
              <Label htmlFor="full_name">Full name</Label>
              <Input id="full_name" required value={fullName} onChange={(event) => setFullName(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email (optional)</Label>
              <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              <p className="text-[11px] text-muted-foreground">
                Used to attribute commits to this candidate in the git history.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="github_login">GitHub username (optional)</Label>
              <Input id="github_login" value={githubLogin} onChange={(event) => setGithubLogin(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="headline">Headline (optional)</Label>
              <Input id="headline" value={headline} onChange={(event) => setHeadline(event.target.value)} placeholder="Final-year CS student" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Add candidate</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
