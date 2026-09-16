"use client";

import { GraduationCap, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { AuthLayout } from "@/components/auth-layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { register } = useAuth();

  const [role, setRole] = React.useState<"STUDENT" | "INTERVIEWER">(
    params.get("role") === "interviewer" ? "INTERVIEWER" : "STUDENT",
  );
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [organization, setOrganization] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const profile = await register({
        email,
        password,
        full_name: fullName,
        role,
        organization_name: role === "INTERVIEWER" ? organization || undefined : undefined,
      });
      router.push(homeFor(profile.user.role));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Registration failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="Analyse repositories with evidence you can check.">
      <form onSubmit={onSubmit} className="space-y-4">
        {error ? <Alert tone="danger" title="Could not register">{error}</Alert> : null}

        <fieldset className="space-y-1.5">
          <Label asChild>
            <legend>I am</legend>
          </Label>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { value: "STUDENT", label: "A candidate", icon: GraduationCap },
                { value: "INTERVIEWER", label: "Hiring", icon: Users },
              ] as const
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setRole(option.value)}
                aria-pressed={role === option.value}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs transition-colors",
                  role === option.value
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border text-muted-foreground hover:bg-muted/50",
                )}
              >
                <option.icon className="size-4" />
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="space-y-1.5">
          <Label htmlFor="full_name">Full name</Label>
          <Input
            id="full_name"
            required
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Alex Mehta"
          />
        </div>
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
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 10 characters"
          />
          <p className="text-[11px] text-muted-foreground">
            Minimum 10 characters, mixing letters with numbers or symbols.
          </p>
        </div>
        {role === "INTERVIEWER" ? (
          <div className="space-y-1.5">
            <Label htmlFor="organization">Team or company name</Label>
            <Input
              id="organization"
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
              placeholder="Acme Hiring"
            />
            <p className="text-[11px] text-muted-foreground">
              Creates a workspace for your candidates, jobs and scoring policies.
            </p>
          </div>
        ) : null}

        <Button type="submit" className="w-full" loading={submitting}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-xs text-muted-foreground">
        Already registered?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}

export default function RegisterPage() {
  return (
    <React.Suspense fallback={null}>
      <RegisterForm />
    </React.Suspense>
  );
}
