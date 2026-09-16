"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { api, tokenStore } from "./api";
import type { Me, Role } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<Me>;
  register: (input: {
    email: string;
    password: string;
    full_name: string;
    role: "STUDENT" | "INTERVIEWER";
    organization_name?: string;
  }) => Promise<Me>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = React.useState<Me | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    if (!tokenStore.access) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api.auth.me());
      setError(null);
    } catch {
      tokenStore.clear();
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = React.useCallback(async (email: string, password: string) => {
    const response = await api.auth.login({ email, password });
    tokenStore.set(response.tokens);
    const profile = await api.auth.me();
    setMe(profile);
    return profile;
  }, []);

  const register = React.useCallback<AuthState["register"]>(async (input) => {
    const response = await api.auth.register(input);
    tokenStore.set(response.tokens);
    const profile = await api.auth.me();
    setMe(profile);
    return profile;
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      /* the session is being discarded either way */
    }
    tokenStore.clear();
    setMe(null);
  }, []);

  const value = React.useMemo(
    () => ({ me, loading, error, refresh, login, register, logout }),
    [me, loading, error, refresh, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Home route for a role, used after sign-in and by the route guard. */
export function homeFor(role: Role): string {
  if (role === "INTERVIEWER") return "/interviewer";
  if (role === "ADMIN") return "/admin";
  return "/student";
}

/**
 * Client-side route guard. The API enforces authorisation independently — this
 * only prevents rendering a page the user cannot use.
 */
export function useRequireRole(roles: Role[]) {
  const { me, loading } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (loading) return;
    if (!me) {
      router.replace("/login");
      return;
    }
    if (!roles.includes(me.user.role) && me.user.role !== "ADMIN") {
      router.replace(homeFor(me.user.role));
    }
  }, [me, loading, roles, router]);

  return { me, loading };
}
