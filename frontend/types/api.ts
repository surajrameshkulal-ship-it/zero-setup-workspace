export type ScanStatus = "queued" | "running" | "completed" | "failed";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type RuleSeverity = "info" | "low" | "medium" | "high" | "critical";

export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: "admin" | "member" | "viewer";
  is_active: boolean;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: User;
};

export type Repository = {
  id: string;
  organization_id: string;
  github_installation_id: string | null;
  github_repository_id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ScanListItem = {
  id: string;
  repository_id: string;
  repository_full_name: string | null;
  github_pr_number: number;
  github_pr_url: string | null;
  title: string | null;
  status: ScanStatus;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  findings_count: number;
  created_at: string;
  completed_at: string | null;
};

export type Finding = {
  title?: string;
  description?: string;
  severity?: RuleSeverity | string;
  path?: string;
  line?: number;
  source?: string;
  category?: string;
  [key: string]: unknown;
};

export type ScanDetail = ScanListItem & {
  organization_id: string;
  head_sha: string;
  base_sha: string | null;
  github_check_run_id: number | null;
  trigger: string;
  files_changed: number;
  lines_added: number;
  lines_deleted: number;
  summary: string | null;
  failure_reason: string | null;
  semgrep_findings: Finding[];
  ai_findings: Finding[];
  company_rule_violations: Finding[];
  architecture_violations: Finding[];
  report: Record<string, unknown>;
  ai_review: Record<string, unknown> | null;
  ai_review_markdown: string | null;
  started_at: string | null;
  updated_at: string;
};

export type DashboardResponse = {
  summary: {
    total_repositories: number;
    total_scans: number;
    completed_scans: number;
    failed_scans: number;
    high_risk_scans: number;
    average_risk_score: number;
  };
  recent_scans: DashboardRecentScan[];
};

export type DashboardRecentScan = {
  scan_id: string;
  repository_id: string;
  repository: string;
  pr_number: number;
  title: string | null;
  status: ScanStatus;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  findings_count: number;
  created_at: string;
};

export type CompanyRule = {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  rule_type: "forbidden_text" | "required_text" | "regex" | "file_path";
  pattern: string;
  severity: RuleSeverity;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ArchitectureRule = {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  source_path_pattern: string;
  forbidden_import_pattern: string;
  severity: RuleSeverity;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type HealthStatus = {
  status: string;
  app_status: string;
  database_status: string;
  redis_status: string;
  celery_queue_reachable: boolean;
  timestamp: string;
};

export type QueueMetrics = {
  pending_scan_task_count: number;
  dead_letter_count: number;
  redis_connected: boolean;
  queue_name: string;
};

export type DeadLetterScan = {
  scan_id: string;
  repository_id: string;
  pull_request_number: number;
  head_sha: string;
  error_message: string;
  failed_at: string;
  retry_count: number;
};
