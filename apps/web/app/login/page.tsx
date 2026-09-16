"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { AuthLayout } from "@/components/auth-layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login, me, loading: authLoading } = useAuth();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!authLoading && me) router.replace(homeFor(me.user.role));
  }, [me, authLoading, router]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const profile = await login(email, password);
      router.push(homeFor(profile.user.role));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Sign-in failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title="Sign in to RepoLens" subtitle="Evidence-backed engineering evaluation.">
      <form onSubmit={onSubmit} className="space-y-4">
        {error ? <Alert tone="danger" title="Could not sign in">{error}</Alert> : null}
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="••••••••••"
          />
        </div>
        <Button type="submit" className="w-full" loading={submitting}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-xs text-muted-foreground">
        No account?{" "}
        <Link href="/register" className="text-primary hover:underline">
          Create one
        </Link>
      </p>
    </AuthLayout>
  );
}
