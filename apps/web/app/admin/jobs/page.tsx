"use client";

import * as React from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { relativeTime, titleCase } from "@/lib/utils";

const STATUSES = ["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"];

export default function AdminJobsPage() {
  const [status, setStatus] = React.useState("");
  const jobs = useAsync(
    () => api.admin.jobs({ limit: "100", ...(status ? { status } : {}) }),
    [status],
  );
  const failures = useAsync(() => api.admin.failures(), []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Analysis jobs</CardTitle>
            <CardDescription>{jobs.data?.total ?? 0} total</CardDescription>
          </div>
          <Select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-8 w-40 text-xs"
            aria-label="Filter by status"
          >
            <option value="">Any status</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>{titleCase(value)}</option>
            ))}
          </Select>
        </CardHeader>
        <CardContent className="p-0">
          {jobs.loading ? (
            <DashboardSkeleton />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Repository</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Worker</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(jobs.data?.items ?? []).length === 0 ? (
                  <TableEmpty colSpan={6}>No jobs match this filter.</TableEmpty>
                ) : (
                  (jobs.data?.items ?? []).map((job: any) => (
                    <TableRow key={job.id}>
                      <TableCell className="font-medium">{job.repository}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            job.status === "COMPLETED"
                              ? "success"
                              : job.status === "FAILED"
                                ? "danger"
                                : job.status === "RUNNING"
                                  ? "info"
                                  : "default"
                          }
                        >
                          {titleCase(job.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {job.current_stage ?? "—"}
                        {job.error ? (
                          <p className="mt-0.5 max-w-sm truncate text-danger" title={job.error}>
                            {job.error}
                          </p>
                        ) : null}
                      </TableCell>
                      <TableCell className="font-mono text-[11px] text-muted-foreground">
                        {job.worker || "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {job.duration_seconds ? `${job.duration_seconds.toFixed(1)}s` : "—"}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {relativeTime(job.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Analyzer failures</CardTitle>
          <CardDescription>
            An analyzer that fails inside an otherwise successful run. The affected dimension is
            reported as unavailable rather than estimated.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {(failures.data ?? []).length === 0 ? (
            <p className="p-5 text-xs text-muted-foreground">No analyzer failures recorded.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Analyzer</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead className="text-right">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(failures.data ?? []).map((failure: any) => (
                  <TableRow key={failure.id}>
                    <TableCell className="font-mono text-xs">{failure.analyzer}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {failure.category ? titleCase(failure.category) : "—"}
                    </TableCell>
                    <TableCell className="max-w-md truncate text-xs" title={failure.reason}>
                      {failure.reason}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(failure.created_at)}
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
