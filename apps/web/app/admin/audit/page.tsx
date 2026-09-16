"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

export default function AuditPage() {
  const [action, setAction] = React.useState("");
  const logs = useAsync(
    () => api.admin.auditLogs({ limit: "200", ...(action ? { action } : {}) }),
    [action],
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>
            Append-only record of evaluation creation, scoring, reviewer overrides, candidate access,
            report generation and repository access.
          </CardDescription>
        </div>
        <Input
          value={action}
          onChange={(event) => setAction(event.target.value)}
          placeholder="Filter by action"
          className="h-8 w-52 text-xs"
          aria-label="Filter by action"
        />
      </CardHeader>
      <CardContent className="p-0">
        {logs.loading ? (
          <DashboardSkeleton />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead className="text-right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(logs.data?.items ?? []).length === 0 ? (
                <TableEmpty colSpan={5}>No audit entries match.</TableEmpty>
              ) : (
                (logs.data?.items ?? []).map((entry: any) => (
                  <TableRow key={entry.id}>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">{entry.action}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {entry.actor_email || "system"}
                      {entry.actor_role ? (
                        <span className="ml-1 text-muted-foreground">({entry.actor_role.toLowerCase()})</span>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground">
                      {entry.target_type}
                      {entry.target_id ? `:${String(entry.target_id).slice(0, 8)}` : ""}
                    </TableCell>
                    <TableCell className="max-w-sm truncate font-mono text-[11px] text-muted-foreground">
                      {Object.keys(entry.detail ?? {}).length > 0 ? JSON.stringify(entry.detail) : "—"}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(entry.created_at)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
