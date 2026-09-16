import { FileSearch } from "lucide-react";
import Link from "next/link";
import * as React from "react";

/** Shared chrome for the sign-in and registration pages. */
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-12">
      <div className="grid-backdrop absolute inset-0" aria-hidden />
      <div className="relative w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2">
          <div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <FileSearch className="size-4" />
          </div>
          <span className="text-base font-semibold tracking-tight">RepoLens</span>
        </Link>
        <div className="panel p-6">
          <div className="mb-6 space-y-1 text-center">
            <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
