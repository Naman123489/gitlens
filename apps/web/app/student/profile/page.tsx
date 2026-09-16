"use client";

import { FileUp, Github, ShieldCheck, Unlink } from "lucide-react";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { relativeTime, titleCase } from "@/lib/utils";

const PURPOSES = [
  "debugging",
  "documentation",
  "boilerplate",
  "testing",
  "refactoring",
  "code_review",
  "learning",
  "architecture",
  "core_algorithms",
] as const;

export default function ProfilePage() {
  const { me, refresh, loading } = useAuth();
  const candidateId = me?.candidate_id ?? null;

  const disclosure = useAsync(
    () => api.candidates.disclosure(candidateId as string),
    [candidateId],
    { enabled: Boolean(candidateId) },
  );

  const [usedAi, setUsedAi] = React.useState<boolean | null>(null);
  const [purposes, setPurposes] = React.useState<string[]>([]);
  const [tools, setTools] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [resumeBusy, setResumeBusy] = React.useState(false);
  const [resumeResult, setResumeResult] = React.useState<any>(null);

  React.useEffect(() => {
    if (!disclosure.data) return;
    setUsedAi(disclosure.data.used_ai ?? null);
    setPurposes(disclosure.data.purposes ?? []);
    setTools((disclosure.data.tools ?? []).join(", "));
    setNotes(disclosure.data.notes ?? "");
  }, [disclosure.data]);

  if (loading) return <DashboardSkeleton />;

  const saveDisclosure = async () => {
    if (!candidateId || usedAi === null) return;
    setSaving(true);
    setMessage(null);
    try {
      await api.candidates.setDisclosure(candidateId, {
        used_ai: usedAi,
        purposes,
        tools: tools.split(",").map((tool) => tool.trim()).filter(Boolean).slice(0, 10),
        notes,
      });
      setMessage({ tone: "success", text: "Disclosure saved." });
      disclosure.reload();
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not save the disclosure.",
      });
    } finally {
      setSaving(false);
    }
  };

  const uploadResume = async (file: File) => {
    if (!candidateId) return;
    setResumeBusy(true);
    setMessage(null);
    try {
      setResumeResult(await api.candidates.uploadResume(candidateId, file));
      setMessage({ tone: "success", text: "Résumé processed." });
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not process the résumé.",
      });
    } finally {
      setResumeBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {message ? <Alert tone={message.tone === "success" ? "success" : "danger"}>{message.text}</Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>Connected accounts</CardTitle>
          <CardDescription>
            GitHub tokens are encrypted at rest and never sent to the browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(me?.github_accounts.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground">No GitHub account is connected.</p>
          ) : (
            me?.github_accounts.map((account) => (
              <div key={account.id} className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
                <div className="flex items-center gap-3">
                  <Github className="size-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{account.login}</p>
                    <p className="text-[11px] text-muted-foreground">
                      connected {relativeTime(account.connected_at)} · scopes {account.scopes || "none"}
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await api.auth.disconnectGithub(account.id);
                    await refresh();
                  }}
                >
                  <Unlink className="size-3.5" />
                  Disconnect
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-primary" />
            AI usage disclosure
          </CardTitle>
          <CardDescription>
            Voluntary and written by you. It is stored separately from the analysis and is never used
            as evidence against you — declaring AI use is normal and is not misconduct.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <fieldset className="space-y-2">
            <Label asChild><legend>Did you use AI assistance on your projects?</legend></Label>
            <div className="flex gap-2">
              {[
                { value: true, label: "Yes" },
                { value: false, label: "No" },
              ].map((option) => (
                <Button
                  key={String(option.value)}
                  type="button"
                  size="sm"
                  variant={usedAi === option.value ? "default" : "secondary"}
                  onClick={() => setUsedAi(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </fieldset>

          {usedAi ? (
            <>
              <fieldset className="space-y-2">
                <Label asChild><legend>What did you use it for?</legend></Label>
                <div className="flex flex-wrap gap-1.5">
                  {PURPOSES.map((purpose) => {
                    const active = purposes.includes(purpose);
                    return (
                      <Button
                        key={purpose}
                        type="button"
                        size="sm"
                        variant={active ? "default" : "secondary"}
                        onClick={() =>
                          setPurposes((current) =>
                            active ? current.filter((item) => item !== purpose) : [...current, purpose],
                          )
                        }
                      >
                        {titleCase(purpose)}
                      </Button>
                    );
                  })}
                </div>
              </fieldset>

              <div className="space-y-1.5">
                <Label htmlFor="tools">Tools used (optional)</Label>
                <Input
                  id="tools"
                  value={tools}
                  onChange={(event) => setTools(event.target.value)}
                  placeholder="Claude Code, Copilot"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="notes">Anything you want a reviewer to know (optional)</Label>
                <Textarea
                  id="notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={3}
                  placeholder="For example: which parts you wrote yourself, and how you verified generated code."
                />
              </div>
            </>
          ) : null}

          <Button onClick={saveDisclosure} loading={saving} disabled={usedAi === null}>
            Save disclosure
          </Button>

          {disclosure.data?.comparison ? (
            <Alert tone="info" title="How this compares with repository signals">
              <p>{disclosure.data.comparison.detail}</p>
              <p className="mt-2 text-[11px] italic">{disclosure.data.comparison.limitation}</p>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Résumé</CardTitle>
          <CardDescription>
            Uploading a résumé lets RepoLens compare claimed skills with repository evidence. Gaps are
            reported as “verification recommended”, never as false claims.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface-raised px-4 py-2 text-sm hover:bg-muted">
            <FileUp className="size-4" />
            {resumeBusy ? "Processing…" : "Upload PDF, Markdown or text"}
            <input
              type="file"
              accept=".pdf,.md,.txt,.markdown"
              className="sr-only"
              disabled={resumeBusy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void uploadResume(file);
              }}
            />
          </label>

          {resumeResult ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                {resumeResult.filename} · {resumeResult.word_count} words ·{" "}
                {Object.keys(resumeResult.skills ?? {}).length} skills recognised
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(resumeResult.skills ?? {}).map(([key, value]: [string, any]) => (
                  <Badge key={key} variant="outline">
                    {value.label}
                    {value.claimed_level ? ` · ${value.claimed_level}` : ""}
                  </Badge>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground">{resumeResult.note}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
