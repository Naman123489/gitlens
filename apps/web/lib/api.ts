"use client";

import type {
  Analysis,
  AnalysisJob,
  Candidate,
  Evaluation,
  Evidence,
  GitHubRepository,
  InterviewSession,
  Job,
  Me,
  Page,
  Policy,
  Readiness,
  Recommendation,
  Repository,
  SecurityFinding,
  StudentDashboard,
  TokenPair,
  User,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "repolens.access_token";
const REFRESH_KEY = "repolens.refresh_token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = "error",
    readonly detail: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const tokenStore = {
  get access() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(tokens: TokenPair) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  },
  clear() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

let refreshInFlight: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return false;
  // One refresh at a time: several 401s arriving together must not trigger
  // several refreshes, which would invalidate each other.
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!response.ok) {
        tokenStore.clear();
        return false;
      }
      tokenStore.set((await response.json()) as TokenPair);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  raw?: boolean;
  retry?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, raw, retry = true, headers, ...rest } = options;
  const token = tokenStore.access;

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(body !== undefined ? { "content-type": "application/json" } : {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retry && tokenStore.refresh) {
    if (await refreshTokens()) {
      return request<T>(path, { ...options, retry: false });
    }
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code = "error";
    let detail: Record<string, unknown> = {};
    try {
      const payload = await response.json();
      message = payload?.error?.message ?? message;
      code = payload?.error?.code ?? code;
      detail = payload?.error?.detail ?? {};
    } catch {
      /* the body was not JSON; keep the generic message */
    }
    throw new ApiError(message, response.status, code, detail);
  }

  if (raw) return (await response.text()) as unknown as T;
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const token = tokenStore.access;
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(
      payload?.error?.message ?? "Upload failed",
      response.status,
      payload?.error?.code ?? "error",
    );
  }
  return (await response.json()) as T;
}

export const api = {
  auth: {
    register: (body: {
      email: string;
      password: string;
      full_name: string;
      role: "STUDENT" | "INTERVIEWER";
      organization_name?: string;
    }) => request<{ user: User; tokens: TokenPair }>("/auth/register", { method: "POST", body }),
    login: (body: { email: string; password: string }) =>
      request<{ user: User; tokens: TokenPair }>("/auth/login", { method: "POST", body }),
    me: () => request<Me>("/auth/me"),
    logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),
    githubAuthorize: () =>
      request<{ authorize_url: string; state: string; scopes: string; configured: boolean; note: string | null }>(
        "/auth/github/authorize",
      ),
    disconnectGithub: (accountId: string) =>
      request<{ message: string }>(`/auth/github/${accountId}`, { method: "DELETE" }),
  },
  repositories: {
    listGithub: () => request<GitHubRepository[]>("/github/repositories"),
    import: (full_name: string, candidate_id?: string) =>
      request<Repository>("/repositories/import", { method: "POST", body: { full_name, candidate_id } }),
    list: (params: { candidate_id?: string; limit?: number; offset?: number } = {}) =>
      request<Page<Repository>>(`/repositories?${new URLSearchParams(params as never)}`),
    get: (id: string) => request<Repository>(`/repositories/${id}`),
    remove: (id: string) => request<{ message: string }>(`/repositories/${id}`, { method: "DELETE" }),
    analyze: (id: string, force = false) =>
      request<AnalysisJob>(`/repositories/${id}/analyze`, { method: "POST", body: { force } }),
    jobs: (id: string) => request<AnalysisJob[]>(`/repositories/${id}/jobs`),
    analysis: (id: string) => request<Analysis>(`/repositories/${id}/analysis`),
    analyses: (id: string) => request<Analysis[]>(`/repositories/${id}/analyses`),
    security: (id: string) => request<SecurityFinding[]>(`/repositories/${id}/security`),
    similarity: (id: string) => request<any[]>(`/repositories/${id}/similarity`),
    commits: (id: string) => request<any[]>(`/repositories/${id}/commits`),
    files: (id: string) => request<any[]>(`/repositories/${id}/files`),
  },
  analysisJobs: {
    get: (id: string) => request<AnalysisJob>(`/analysis-jobs/${id}`),
    cancel: (id: string) => request<AnalysisJob>(`/analysis-jobs/${id}/cancel`, { method: "POST" }),
  },
  jobs: {
    list: (params: Record<string, string> = {}) =>
      request<Page<Job>>(`/jobs?${new URLSearchParams(params)}`),
    get: (id: string) => request<Job>(`/jobs/${id}`),
    create: (body: { title: string; description: string; location?: string; is_public?: boolean }) =>
      request<Job>("/jobs", { method: "POST", body }),
    update: (id: string, body: Record<string, unknown>) =>
      request<Job>(`/jobs/${id}`, { method: "PATCH", body }),
    remove: (id: string) => request<{ message: string }>(`/jobs/${id}`, { method: "DELETE" }),
    parse: (body: { title: string; description: string }) =>
      request<{
        requirements: any[];
        responsibilities: string[];
        experience_level: string;
        min_years_experience: number | null;
        domain: string;
        technologies: string[];
        notes: string[];
      }>("/jobs/parse", { method: "POST", body }),
    skills: () => request<{ key: string; label: string; dimension: string; aliases: string[] }[]>(
      "/jobs/taxonomy/skills",
    ),
  },
  evaluations: {
    create: (body: { repository_id: string; job_id?: string; candidate_id?: string; policy_id?: string }) =>
      request<Evaluation>("/evaluations", { method: "POST", body }),
    list: (params: Record<string, string> = {}) =>
      request<Page<Evaluation>>(`/evaluations?${new URLSearchParams(params)}`),
    get: (id: string) => request<Evaluation>(`/evaluations/${id}`),
    evidence: (id: string, params: Record<string, string> = {}) =>
      request<Evidence[]>(`/evaluations/${id}/evidence?${new URLSearchParams(params)}`),
    notes: (id: string) => request<any[]>(`/evaluations/${id}/notes`),
    addNote: (id: string, body: { body: string; category?: string; visible_to_candidate?: boolean }) =>
      request<any>(`/evaluations/${id}/notes`, { method: "POST", body }),
    overrides: (id: string) => request<any[]>(`/evaluations/${id}/overrides`),
    addOverride: (
      id: string,
      body: { target_type: string; target_key: string; new_value: Record<string, unknown>; rationale: string },
    ) => request<any>(`/evaluations/${id}/overrides`, { method: "POST", body }),
    compare: (evaluation_ids: string[]) =>
      request<any>("/evaluations/compare", { method: "POST", body: { evaluation_ids } }),
  },
  candidates: {
    list: (params: Record<string, string> = {}) =>
      request<Page<Candidate>>(`/candidates?${new URLSearchParams(params)}`),
    get: (id: string) => request<any>(`/candidates/${id}`),
    create: (body: { full_name: string; email?: string; github_login?: string; headline?: string }) =>
      request<Candidate>("/candidates", { method: "POST", body }),
    uploadResume: (id: string, file: File) => upload<any>(`/candidates/${id}/resume`, file),
    disclosure: (id: string) => request<any>(`/candidates/${id}/disclosure`),
    setDisclosure: (id: string, body: Record<string, unknown>) =>
      request<any>(`/candidates/${id}/disclosure`, { method: "PUT", body }),
  },
  interviews: {
    list: (params: Record<string, string> = {}) =>
      request<InterviewSession[]>(`/interviews?${new URLSearchParams(params)}`),
    get: (id: string) => request<InterviewSession>(`/interviews/${id}`),
    create: (body: {
      evaluation_id?: string;
      repository_id?: string;
      candidate_id?: string;
      title?: string;
      question_count?: number;
    }) => request<InterviewSession>("/interviews", { method: "POST", body }),
    addQuestions: (id: string, count = 5) =>
      request<any[]>(`/interviews/${id}/questions?count=${count}`, { method: "POST" }),
    answer: (id: string, body: { question_id: string; answer_text: string }) =>
      request<any>(`/interviews/${id}/answers`, { method: "POST", body }),
    review: (id: string, answerId: string, body: { reviewer_score: number; reviewer_comment?: string }) =>
      request<any>(`/interviews/${id}/answers/${answerId}/review`, { method: "POST", body }),
    complete: (id: string) => request<InterviewSession>(`/interviews/${id}/complete`, { method: "POST" }),
  },
  policies: {
    list: (params: Record<string, string> = {}) =>
      request<Policy[]>(`/policies?${new URLSearchParams(params)}`),
    presets: () => request<any[]>("/policies/presets"),
    create: (body: {
      name: string;
      description?: string;
      weights: Record<string, number>;
    }) => request<Policy>("/policies", { method: "POST", body }),
    versions: (id: string) => request<Policy[]>(`/policies/${id}/versions`),
  },
  student: {
    dashboard: () => request<StudentDashboard>("/me/dashboard"),
    readiness: (jobId?: string) =>
      request<Readiness>(`/me/readiness${jobId ? `?job_id=${jobId}` : ""}`),
    recommendations: () => request<Recommendation[]>("/me/recommendations"),
  },
  reports: {
    json: (evaluationId: string) => request<any>(`/reports/${evaluationId}`),
    markdown: (evaluationId: string) =>
      request<string>(`/reports/${evaluationId}/markdown`, { raw: true }),
  },
  admin: {
    health: () => request<any>("/admin/health"),
    analyzers: () => request<any>("/admin/analyzers"),
    auditLogs: (params: Record<string, string> = {}) =>
      request<Page<any>>(`/admin/audit-logs?${new URLSearchParams(params)}`),
    jobs: (params: Record<string, string> = {}) =>
      request<Page<any>>(`/admin/jobs?${new URLSearchParams(params)}`),
    failures: () => request<any[]>("/admin/analyzer-failures"),
    users: (params: Record<string, string> = {}) =>
      request<Page<any>>(`/admin/users?${new URLSearchParams(params)}`),
  },
};
