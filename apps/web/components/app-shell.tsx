"use client";

import {
  Activity,
  BarChart3,
  Briefcase,
  ClipboardList,
  FileSearch,
  FolderGit2,
  Gauge,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  ScrollText,
  Settings2,
  ShieldCheck,
  Target,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth-context";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  roles: Role[];
}

const NAV: NavItem[] = [
  { href: "/student", label: "Overview", icon: LayoutDashboard, roles: ["STUDENT"] },
  { href: "/student/repositories", label: "Repositories", icon: FolderGit2, roles: ["STUDENT"] },
  { href: "/student/readiness", label: "Job readiness", icon: Target, roles: ["STUDENT"] },
  { href: "/student/improve", label: "Improvement plan", icon: BarChart3, roles: ["STUDENT"] },
  { href: "/student/interview-prep", label: "Interview prep", icon: MessagesSquare, roles: ["STUDENT"] },
  { href: "/student/profile", label: "Profile & disclosure", icon: ShieldCheck, roles: ["STUDENT"] },

  { href: "/interviewer", label: "Overview", icon: LayoutDashboard, roles: ["INTERVIEWER"] },
  { href: "/interviewer/candidates", label: "Candidates", icon: Users, roles: ["INTERVIEWER"] },
  { href: "/interviewer/jobs", label: "Jobs", icon: Briefcase, roles: ["INTERVIEWER"] },
  { href: "/interviewer/evaluations", label: "Evaluations", icon: FileSearch, roles: ["INTERVIEWER"] },
  { href: "/interviewer/interviews", label: "Verification", icon: ClipboardList, roles: ["INTERVIEWER"] },
  { href: "/interviewer/policies", label: "Scoring policies", icon: Settings2, roles: ["INTERVIEWER"] },

  { href: "/admin", label: "System health", icon: Activity, roles: ["ADMIN"] },
  { href: "/admin/analyzers", label: "Analyzers", icon: Gauge, roles: ["ADMIN"] },
  { href: "/admin/jobs", label: "Analysis jobs", icon: FolderGit2, roles: ["ADMIN"] },
  { href: "/admin/audit", label: "Audit log", icon: ScrollText, roles: ["ADMIN"] },
  { href: "/admin/users", label: "Users", icon: Users, roles: ["ADMIN"] },
];

export function AppShell({
  children,
  role,
  title,
  subtitle,
  actions,
}: {
  children: React.ReactNode;
  role: Role;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const items = NAV.filter((item) => item.roles.includes(role));
  const adminItems = me?.user.role === "ADMIN" && role !== "ADMIN"
    ? NAV.filter((item) => item.roles.includes("ADMIN")).slice(0, 1)
    : [];

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <TooltipProvider>
      <div className="flex min-h-screen bg-background">
        {/* Sidebar — permanent on desktop, a drawer below lg. */}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-border bg-surface transition-transform lg:static lg:translate-x-0",
            mobileOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="flex h-14 items-center justify-between border-b border-border px-4">
            <Link href="/" className="flex items-center gap-2">
              <div className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
                <FileSearch className="size-4" />
              </div>
              <span className="text-sm font-semibold tracking-tight">RepoLens</span>
            </Link>
            <button
              type="button"
              className="rounded-md p-1 text-muted-foreground hover:bg-muted lg:hidden"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X className="size-4" />
            </button>
          </div>

          <nav className="flex-1 space-y-1 overflow-y-auto p-3" aria-label="Main">
            {items.map((item) => {
              const active = pathname === item.href || (item.href !== `/${role.toLowerCase()}` && pathname.startsWith(`${item.href}/`));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-surface-raised font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <item.icon className="size-4" />
                  {item.label}
                </Link>
              );
            })}
            {adminItems.length > 0 ? (
              <>
                <p className="px-3 pb-1 pt-4 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Administration
                </p>
                {adminItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </Link>
                ))}
              </>
            ) : null}
          </nav>

          <div className="border-t border-border p-3">
            <div className="mb-2 flex items-center gap-2 px-1">
              <div className="grid size-7 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium">
                {(me?.user.full_name ?? "?").slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{me?.user.full_name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{me?.user.email}</p>
              </div>
              <Badge variant="outline" className="shrink-0 text-[10px]">
                {me?.user.role.toLowerCase()}
              </Badge>
            </div>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={handleLogout}>
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        </aside>

        {mobileOpen ? (
          <div
            className="fixed inset-0 z-30 bg-black/60 lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur lg:px-8">
            <button
              type="button"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="size-4" />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-sm font-semibold">{title}</h1>
              {subtitle ? <p className="truncate text-xs text-muted-foreground">{subtitle}</p> : null}
            </div>
            {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
          </header>

          <main className="flex-1 px-4 py-6 lg:px-8">
            <div className="mx-auto max-w-[1400px]">{children}</div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
