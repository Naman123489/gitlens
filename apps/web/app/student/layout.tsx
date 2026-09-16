"use client";

import { AppShell } from "@/components/app-shell";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useRequireRole } from "@/lib/auth-context";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useRequireRole(["STUDENT"]);

  if (loading || !me) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-16">
        <DashboardSkeleton />
      </div>
    );
  }

  return (
    <AppShell
      role="STUDENT"
      title="Your engineering profile"
      subtitle={me.user.full_name}
    >
      {children}
    </AppShell>
  );
}
