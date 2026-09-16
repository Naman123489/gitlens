"use client";

import { History, Plus, Settings2 } from "lucide-react";
import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { ApiError, api } from "@/lib/api";
import { relativeTime, titleCase } from "@/lib/utils";

const CATEGORIES = [
  "technical_quality",
  "architecture",
  "job_relevance",
  "ownership",
  "testing",
  "documentation",
  "git_engineering",
  "security",
  "ai_utilization",
] as const;

const DEFAULT_WEIGHTS: Record<string, number> = {
  technical_quality: 0.2,
  architecture: 0.15,
  job_relevance: 0.2,
  ownership: 0.15,
  testing: 0.1,
  documentation: 0.05,
  git_engineering: 0.05,
  security: 0.05,
  ai_utilization: 0.05,
};

export default function PoliciesPage() {
  const policies = useAsync(() => api.policies.list(), []);
  const presets = useAsync(() => api.policies.presets(), []);

  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [weights, setWeights] = React.useState<Record<string, number>>({ ...DEFAULT_WEIGHTS });
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const policy = await api.policies.create({ name, description, weights });
      setMessage({
        tone: "success",
        text: `Saved “${policy.name}” as version ${policy.version}. Earlier versions stay readable so past evaluations remain explainable.`,
      });
      setName("");
      setDescription("");
      policies.reload();
    } catch (caught) {
      setMessage({
        tone: "danger",
        text: caught instanceof ApiError ? caught.message : "Could not save the policy.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {message ? <Alert tone={message.tone === "success" ? "success" : "danger"}>{message.text}</Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>Presets</CardTitle>
          <CardDescription>
            Ready-made weightings. Select one to load it into the editor below.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {(presets.data ?? []).map((preset: any) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => {
                setName(preset.name);
                setDescription(preset.description);
                setWeights(preset.weights);
              }}
              className="panel-raised p-4 text-left transition-colors hover:bg-muted/40"
            >
              <p className="text-sm font-semibold">{preset.name}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{preset.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {Object.entries(preset.weights as Record<string, number>)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 4)
                  .map(([category, weight]) => (
                    <Badge key={category} variant="outline" className="text-[10px]">
                      {titleCase(category)} {(weight * 100).toFixed(0)}%
                    </Badge>
                  ))}
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr,380px]">
        <Card>
          <CardHeader>
            <CardTitle>Create or update a policy</CardTitle>
            <CardDescription>
              Weights do not need to sum to 1 — they are normalised. Saving a policy with an existing
              name creates a new immutable version.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="name">Policy name</Label>
                  <Input id="name" required value={name} onChange={(event) => setName(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="description">Description</Label>
                  <Input
                    id="description"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="When your team should use this"
                  />
                </div>
              </div>

              <div className="space-y-3">
                {CATEGORIES.map((category) => (
                  <div key={category}>
                    <div className="flex items-baseline justify-between gap-3">
                      <Label htmlFor={`weight-${category}`}>{titleCase(category)}</Label>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {((weights[category] ?? 0) * 100).toFixed(0)}%
                        {total > 0 ? ` → ${(((weights[category] ?? 0) / total) * 100).toFixed(0)}% normalised` : ""}
                      </span>
                    </div>
                    <input
                      id={`weight-${category}`}
                      type="range"
                      min={0}
                      max={50}
                      step={1}
                      value={Math.round((weights[category] ?? 0) * 100)}
                      onChange={(event) =>
                        setWeights((current) => ({
                          ...current,
                          [category]: Number(event.target.value) / 100,
                        }))
                      }
                      className="mt-1.5 w-full accent-[hsl(var(--primary))]"
                    />
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="text-xs text-muted-foreground">Total before normalisation</span>
                <span className="text-sm font-medium tabular-nums">{(total * 100).toFixed(0)}%</span>
              </div>

              <div className="flex gap-2">
                <Button type="submit" loading={busy} disabled={total <= 0}>
                  <Plus className="size-4" />
                  Save policy version
                </Button>
                <Button type="button" variant="ghost" onClick={() => setWeights({ ...DEFAULT_WEIGHTS })}>
                  Reset to default
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Your policies</CardTitle>
            <CardDescription>Current versions. Every evaluation records the one it used.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {policies.loading ? (
              <DashboardSkeleton />
            ) : (policies.data ?? []).length === 0 ? (
              <EmptyState
                icon={Settings2}
                title="No custom policies"
                description="Evaluations use the RepoLens default weighting until you define your own."
              />
            ) : (
              (policies.data ?? []).map((policy) => (
                <div key={policy.id} className="rounded-md border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{policy.name}</p>
                      <p className="text-[11px] text-muted-foreground">
                        v{policy.version} · {relativeTime(policy.created_at)}
                        {policy.organization_id ? "" : " · global"}
                      </p>
                    </div>
                    <Badge variant={policy.is_current ? "success" : "default"} className="shrink-0">
                      <History className="size-3" />
                      {policy.is_current ? "current" : "historic"}
                    </Badge>
                  </div>
                  <div className="mt-2 space-y-1">
                    {Object.entries(policy.weights)
                      .sort(([, a], [, b]) => b - a)
                      .slice(0, 4)
                      .map(([category, weight]) => (
                        <div key={category}>
                          <div className="flex justify-between text-[11px] text-muted-foreground">
                            <span>{titleCase(category)}</span>
                            <span className="tabular-nums">{(weight * 100).toFixed(0)}%</span>
                          </div>
                          <Progress value={weight * 100 * 3} className="mt-0.5 h-1" />
                        </div>
                      ))}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
