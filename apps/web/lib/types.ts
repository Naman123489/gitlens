/** Response types mirroring the RepoLens API schemas. */

export type Role = "STUDENT" | "INTERVIEWER" | "ADMIN";

export type VerificationStatus =
  | "CLEAR"
  | "REVIEW_RECOMMENDED"
  | "VERIFICATION_REQUIRED"
  | "ANALYSIS_INCOMPLETE";

export type AIClassification =
  | "AI_ASSISTED"
  | "AI_AUGMENTED"
  | "AI_DEPENDENT"
  | "AI_DOMINATED"
  | "INSUFFICIENT_EVIDENCE";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  is_demo: boolean;
  avatar_url: string | null;
  created_at: string;
  last_login_at: string | null;
}

export interface GitHubAccount {
  id: string;
  login: string;
  name: string | null;
  avatar_url: string | null;
  profile_url: string | null;
  scopes: string;
  can_read_private: boolean;
  connected_at: string | null;
}

export interface Me {
  user: User;
  organizations: { id: string; name: string; slug: string; role: string }[];
  github_accounts: GitHubAccount[];
  candidate_id: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Repository {
  id: string;
  name: string;
  full_name: string;
  description: string | null;
  html_url: string | null;
  primary_language: string | null;
  languages: Record<string, number>;
  topics: string[];
  stars: number;
  forks: number;
  open_issues: number;
  size_kb: number;
  is_private: boolean;
  is_fork: boolean;
  is_archived: boolean;
  default_branch: string;
  license_name: string | null;
  analysis_status: string;
  last_analyzed_at: string | null;
  pushed_at: string | null;
  is_demo: boolean;
}

export interface GitHubRepository {
  external_id: string;
  name: string;
  full_name: string;
  description: string | null;
  html_url: string;
  clone_url: string;
  default_branch: string;
  language: string | null;
  stars: number;
  forks: number;
  size_kb: number;
  private: boolean;
  fork: boolean;
  archived: boolean;
  topics: string[];
  pushed_at: string | null;
  imported: boolean;
  repository_id: string | null;
}

export interface AnalysisStage {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
}

export interface AnalysisJob {
  id: string;
  repository_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  progress: number;
  current_stage: string | null;
  stages: AnalysisStage[];
  error: string | null;
  analysis_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
}

export interface EvidenceDetail {
  detail: string;
  file?: string;
  line?: number;
  snippet?: string;
  metric?: number;
}

export interface Evidence {
  evidence_id: string;
  category: string;
  claim: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  confidence: number;
  supports: "strength" | "weakness" | "neutral";
  tags: string[];
  details: EvidenceDetail[];
  analyzer: string;
}

export interface CategoryScore {
  category: string;
  score: number | null;
  confidence: number;
  weight: number;
  available: boolean;
  unavailable_reason: string | null;
  evidence_ids: string[];
  sub_scores: Record<string, number>;
}

export interface Analysis {
  id: string;
  repository_id: string;
  head_sha: string | null;
  analyzer_version: string;
  repository_score: number | null;
  ownership_confidence: number | null;
  ai_likelihood: number | null;
  ai_classification: AIClassification | null;
  ai_utilization: number | null;
  originality: string | null;
  is_partial: boolean;
  duration_seconds: number;
  category_scores: Record<string, { score: number | null; confidence: number; analyzer: string }>;
  stats: Record<string, any>;
  failures: { analyzer: string; category: string | null; reason: string; occurred_at: string }[];
  limitations: { analyzer?: string; scope: string; detail: string }[];
  created_at: string;
  results?: Record<string, any>;
  evidence?: (Evidence & { id: string })[];
}

export interface SkillMatch {
  skill: string;
  label: string;
  dimension: string;
  required: boolean;
  importance: number;
  strength: number;
  matched: boolean;
  sources: { type: string; detail: string; weight: number }[];
}

export interface Recommendation {
  id?: string;
  category: string;
  title: string;
  detail: string;
  impact: "high" | "medium" | "low";
  effort: "high" | "medium" | "low";
  expected_gain: number | null;
  evidence_ids?: string[];
  repository_id?: string | null;
  evaluation_id?: string | null;
}

export interface Evaluation {
  id: string;
  repository_id: string;
  job_id: string | null;
  candidate_id: string | null;
  overall_score: number | null;
  confidence: number;
  job_match: number | null;
  ownership_confidence: number | null;
  ai_likelihood: number | null;
  ai_utilization: number | null;
  ai_classification: AIClassification | null;
  originality: string | null;
  verification_status: VerificationStatus;
  created_at: string;
  is_demo: boolean;
  verification_reasons: string[];
  limitations: { analyzer?: string; scope: string; detail: string }[];
  failures: { analyzer: string; reason: string }[];
  skill_matches: SkillMatch[];
  engineering_dna: Record<string, number>;
  resume_consistency: ResumeConsistency | null;
  narrative: { text: string; generated_by: string; model?: string | null } | null;
  versions: Record<string, unknown>;
  scores: CategoryScore[];
  policy: { id?: string; name: string; version: number; weights?: Record<string, number> } | null;
  repository: Partial<Repository> & { id: string; full_name: string } | null;
  job: { id: string; title: string; experience_level: string; domain: string; requirements: any[] } | null;
  candidate: { id: string; full_name: string; github_login: string | null; headline: string | null } | null;
  recommendations: Recommendation[];
}

export interface ResumeConsistency {
  items: {
    skill: string;
    label: string;
    claimed_level: string | null;
    expected_evidence: number;
    observed_evidence: number;
    status: "supported" | "partially_supported" | "verification_recommended";
    detail: string;
  }[];
  unclaimed_strengths: { skill: string; label: string; observed_evidence: number }[];
  supported: number;
  partially_supported: number;
  verification_recommended: number;
  claims_total: number;
  limitation: string;
}

export interface JobRequirement {
  skill: string;
  label: string;
  dimension: string;
  required: boolean;
  importance: number;
  source: string;
  matched_terms: string[];
}

export interface Job {
  id: string;
  title: string;
  description: string;
  location: string | null;
  experience_level: string;
  domain: string;
  min_years_experience: number | null;
  responsibilities: string[];
  parse_notes: string[];
  organization_id: string | null;
  policy_id: string | null;
  is_open: boolean;
  is_public: boolean;
  is_demo: boolean;
  created_at: string;
  requirements: JobRequirement[];
}

export interface Candidate {
  id: string;
  full_name: string;
  email: string | null;
  github_login: string | null;
  headline: string | null;
  organization_id: string | null;
  user_id: string | null;
  resume_filename: string | null;
  has_resume: boolean;
  has_disclosure: boolean;
  is_demo: boolean;
  created_at: string;
}

export interface Policy {
  id: string;
  policy_key: string;
  name: string;
  description: string;
  version: number;
  is_current: boolean;
  organization_id: string | null;
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  created_at: string;
}

export interface InterviewQuestion {
  id: string;
  category: string;
  question: string;
  difficulty: string;
  rationale: string;
  anchors: { file?: string; line?: number; detail?: string; metric?: number }[];
  expected_points: string[];
  generated_by: string;
}

export interface InterviewAnswer {
  id: string;
  question_id: string;
  answer_text: string;
  word_count: number;
  score: number | null;
  assessment: {
    score?: number;
    dimensions?: Record<string, { score: number; detail: string }>;
    assessed_by?: string;
    limitation?: string;
    summary?: string;
  };
  assessed_by: string;
  reviewer_score: number | null;
  reviewer_comment: string | null;
}

export interface InterviewSession {
  id: string;
  title: string;
  status: string;
  mode: string;
  evaluation_id: string | null;
  candidate_id: string | null;
  repository_id: string | null;
  verification_score: number | null;
  dimension_scores: Record<string, number>;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
  questions: InterviewQuestion[];
  answers: InterviewAnswer[];
}

export interface SecurityFinding {
  id: string;
  kind: string;
  rule_id: string;
  title: string;
  category: string | null;
  severity: string;
  confidence: number;
  file_path: string;
  line: number;
  masked_value: string | null;
  snippet: string | null;
  remediation: string | null;
  cwe: string | null;
  note: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface StudentDashboard {
  engineering_score: number | null;
  engineering_score_basis: { repositories_analysed: number; method: string };
  repositories: { total: number; analysed: number; pending: number };
  engineering_dna: Record<string, number>;
  strengths: { category: string; score: number; repository_id: string }[];
  weaknesses: { category: string; score: number; repository_id: string }[];
  recommendations: Recommendation[];
  repository_summaries: {
    id: string;
    full_name: string;
    name: string;
    primary_language: string | null;
    analysis_status: string;
    score: number | null;
    ownership_confidence: number | null;
    ai_classification: string | null;
    evaluation_id: string | null;
    last_analyzed_at: string | null;
  }[];
  empty_state: { title: string; detail: string } | null;
}

export interface Readiness {
  roles: {
    role: string;
    readiness: number;
    missing_required: string[];
    evidenced: { skill: string; label: string; strength: number }[];
    per_repository: { repository_id: string; full_name: string; match: number | null; missing: string[] }[];
  }[];
  repositories: number;
  note?: string;
  empty_state?: { title: string; detail: string };
}
