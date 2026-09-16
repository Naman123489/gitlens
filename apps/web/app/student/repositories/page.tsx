"use client";

import { Github, Link2, Loader2, Play, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { relativeTime, titleCase } from "@/lib/utils";

export default function RepositoriesPage() {
  const { me, refresh } = useAuth();
  const [manualName, setManualName] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const imported = useAsync(() => api.repositories.list({ limit: 100 }), []);
  const hasGithub = (me?.github_accounts.length ?? 0) > 0;
  const remote = useAsync(() => api.repositories.listGithub(), [hasGithub], { enabled: hasGithub });

  const connectGithub = async () => {
    try {
      const response = await api.auth.githubAuthorize();
      if (!response.configured) {
        setMessage({
          tone: "danger",
          text:
            response.note ??
            "GitHub OAuth is not configured on this deployment. You can still import any public " +
              "repository by its owner/name below.",
        });
        return;
      }
      window.location.href = response.authorize_url;
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not start GitHub authorisation.",
      });
    }
  };

  const importRepository = async (fullName: string) => {
    setBusy(fullName);
    setMessage(null);
    try {
      await api.repositories.import(fullName);
      setMessage({ tone: "success", text: `Imported ${fullName}.` });
      setManualName("");
      imported.reload();
      remote.reload();
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : `Could not import ${fullName}.`,
      });
    } finally {
      setBusy(null);
    }
  };

  const analyse = async (repositoryId: string) => {
    setBusy(repositoryId);
    try {
      await api.repositories.analyze(repositoryId);
      setMessage({ tone: "success", text: "Analysis queued. Open the repository to watch progress." });
      imported.reload();
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not queue the analysis.",
      });
    } finally {
      setBusy(null);
    }
  };

  const remove = async (repositoryId: string, fullName: string) => {
    if (!window.confirm(`Remove ${fullName} and all of its analyses? This cannot be undone.`)) return;
    setBusy(repositoryId);
    try {
      await api.repositories.remove(repositoryId);
      imported.reload();
    } finally {
      setBusy(null);
    }
  };

  const remoteFiltered = (remote.data ?? []).filter((repo) =>
    repo.full_name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      {message ? (
        <Alert tone={message.tone === "success" ? "success" : "danger"}>{message.text}</Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Add a repository</CardTitle>
          <CardDescription>
            Connect GitHub to list your repositories, or import any public repository directly.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={connectGithub} variant={hasGithub ? "secondary" : "default"}>
              <Github className="size-4" />
              {hasGithub ? "Reconnect GitHub" : "Connect GitHub"}
            </Button>
            {hasGithub ? (
              <span className="text-xs text-muted-foreground">
                Connected as{" "}
                {me?.github_accounts.map((account) => account.login).join(", ")}
                {me?.github_accounts[0]?.can_read_private ? " (private repositories included)" : ""}
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">
                Not connected. Public repositories can still be imported below.
              </span>
            )}
          </div>

          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (manualName.includes("/")) void importRepository(manualName.trim());
            }}
          >
            <Input
              value={manualName}
              onChange={(event) => setManualName(event.target.value)}
              placeholder="owner/repository"
              className="max-w-xs"
              aria-label="Repository owner and name"
            />
            <Button type="submit" variant="secondary" loading={busy === manualName.trim()}>
              <Link2 className="size-4" />
              Import
            </Button>
          </form>
        </CardContent>
      </Card>

      {hasGithub ? (
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-3">
            <div>
              <CardTitle>Your GitHub repositories</CardTitle>
              <CardDescription>Forks and archived repositories are hidden.</CardDescription>
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Filter"
                className="h-8 w-44 pl-8 text-xs"
                aria-label="Filter repositories"
              />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {remote.loading ? (
              <div className="space-y-2 p-5">
                {[0, 1, 2].map((index) => (
                  <Skeleton key={index} className="h-9" />
                ))}
              </div>
            ) : remote.error ? (
              <Alert tone="warning" className="m-5">{remote.error}</Alert>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Repository</TableHead>
                    <TableHead>Language</TableHead>
                    <TableHead className="text-right">Stars</TableHead>
                    <TableHead className="text-right">Updated</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {remoteFiltered.length === 0 ? (
                    <TableEmpty colSpan={5}>No repositories matched.</TableEmpty>
                  ) : (
                    remoteFiltered.slice(0, 40).map((repo) => (
                      <TableRow key={repo.full_name}>
                        <TableCell>
                          <span className="font-medium">{repo.full_name}</span>
                          {repo.private ? (
                            <Badge variant="outline" className="ml-2 text-[10px]">private</Badge>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-muted-foreground">{repo.language ?? "—"}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{repo.stars}</TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">
                          {relativeTime(repo.pushed_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          {repo.imported ? (
                            <Button size="sm" variant="ghost" asChild>
                              <Link href={`/student/repositories/${repo.repository_id}`}>Open</Link>
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="secondary"
                              loading={busy === repo.full_name}
                              onClick={() => importRepository(repo.full_name)}
                            >
                              Import
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Imported repositories</CardTitle>
          <CardDescription>Analysis runs in the background; you can leave this page.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {imported.loading ? (
            <div className="space-y-2 p-5">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-9" />
              ))}
            </div>
          ) : (imported.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              className="m-5"
              icon={Github}
              title="No repositories analysed yet"
              description="Connect GitHub to begin your engineering profile, or import a public repository by name."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Repository</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Last analysed</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {imported.data?.items.map((repo) => (
                  <TableRow key={repo.id}>
                    <TableCell>
                      <Link href={`/student/repositories/${repo.id}`} className="font-medium hover:text-primary">
                        {repo.full_name}
                      </Link>
                      {repo.description ? (
                        <p className="mt-0.5 max-w-md truncate text-xs text-muted-foreground">
                          {repo.description}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          repo.analysis_status === "COMPLETED"
                            ? "success"
                            : repo.analysis_status === "FAILED"
                              ? "danger"
                              : repo.analysis_status === "NOT_ANALYZED"
                                ? "default"
                                : "info"
                        }
                      >
                        {repo.analysis_status === "RUNNING" || repo.analysis_status === "QUEUED" ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : null}
                        {titleCase(repo.analysis_status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(repo.last_analyzed_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={busy === repo.id}
                          onClick={() => analyse(repo.id)}
                        >
                          <Play className="size-3.5" />
                          Analyse
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Remove ${repo.full_name}`}
                          onClick={() => remove(repo.id, repo.full_name)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
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
