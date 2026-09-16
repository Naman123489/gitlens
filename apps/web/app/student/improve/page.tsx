"use client";

import { Lightbulb } from "lucide-react";
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";

const IMPACT_VARIANT = { high: "danger", medium: "warning", low: "default" } as const;

export default function ImprovePage() {
  const { data, loading, error } = useAsync(() => api.student.recommendations(), []);

  if (loading) return <DashboardSkeleton />;
  if (error) return <Alert tone="danger" title="Could not load recommendations">{error}</Alert>;

  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={Lightbulb}
        title="No recommendations yet"
        description="Evaluate a repository against a job to generate an improvement plan derived from its evidence."
      />
    );
  }

  const grouped = data.reduce<Record<string, typeof data>>((accumulator, item) => {
    (accumulator[item.category] ??= []).push(item);
    return accumulator;
  }, {});

  return (
    <div className="space-y-6">
      <Alert tone="info" title="How expected gain is calculated">
        Each suggestion shows the movement in your overall score if that dimension reached 85,
        given the weighting of the policy the evaluation used. It is arithmetic on the real weights,
        not an estimate.
      </Alert>

      {Object.entries(grouped).map(([category, items]) => (
        <Card key={category}>
          <CardHeader>
            <CardTitle>{titleCase(category)}</CardTitle>
            <CardDescription>{items.length} suggestion{items.length === 1 ? "" : "s"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {items.map((item, index) => (
              <div key={`${item.title}-${index}`} className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{item.title}</p>
                    <Badge variant={IMPACT_VARIANT[item.impact]}>{item.impact} impact</Badge>
                    <Badge variant="outline">{item.effort} effort</Badge>
                    {item.expected_gain ? (
                      <Badge variant="success">+{item.expected_gain.toFixed(1)} overall</Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
                  {item.repository_id ? (
                    <Link
                      href={`/student/repositories/${item.repository_id}`}
                      className="mt-1 inline-block text-[11px] text-primary hover:underline"
                    >
                      View the repository
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
