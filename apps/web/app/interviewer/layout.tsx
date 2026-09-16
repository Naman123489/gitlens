"use client";

import { AppShell } from "@/components/app-shell";
import { DashboardSkeleton } from "@/components/ui/skeleton";
import { useRequireRole } from "@/lib/auth-context";

export default function InterviewerLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useRequireRole(["INTERVIEWER"]);

  if (loading || !me) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-16">
        <DashboardSkeleton />
      </div>
    );
  }

  const organization = me.organizations[0];

  return (
    <AppShell
      role="INTERVIEWER"
      title="Hiring workspace"
      subtitle={organization ? organization.name : me.user.full_name}
    >
      {children}
    </AppShell>
  );
}
