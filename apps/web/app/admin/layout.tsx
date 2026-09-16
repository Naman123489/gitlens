"use client";

import { AppShell } from "@/components/app-shell";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useRequireRole } from "@/lib/auth-context";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useRequireRole(["ADMIN"]);

  if (loading || !me) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-16">
        <DashboardSkeleton />
      </div>
    );
  }

  return (
    <AppShell role="ADMIN" title="Administration" subtitle={me.user.email}>
      {children}
    </AppShell>
  );
}
