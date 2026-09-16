"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

export default function AdminUsersPage() {
  const users = useAsync(() => api.admin.users({ limit: "200" }), []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Users</CardTitle>
        <CardDescription>
          {users.data?.total ?? 0} accounts. Administrator accounts are provisioned with
          <code className="mx-1 font-mono text-[11px]">scripts/create_admin.py</code>, never through
          the sign-up form.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {users.loading ? (
          <DashboardSkeleton />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Last sign-in</TableHead>
                <TableHead className="text-right">Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(users.data?.items ?? []).length === 0 ? (
                <TableEmpty colSpan={5}>No users.</TableEmpty>
              ) : (
                (users.data?.items ?? []).map((user: any) => (
                  <TableRow key={user.id}>
                    <TableCell>
                      <p className="text-sm font-medium">{user.full_name}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.role === "ADMIN" ? "accent" : "outline"}>
                        {user.role.toLowerCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Badge variant={user.is_active ? "success" : "danger"}>
                          {user.is_active ? "active" : "deactivated"}
                        </Badge>
                        {user.is_demo ? <Badge variant="warning">demo</Badge> : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(user.last_login_at)}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {relativeTime(user.created_at)}
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
