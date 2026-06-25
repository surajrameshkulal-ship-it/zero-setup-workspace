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

export type EngineeringRequestType =
  | "bug"
  | "feature"
  | "refactor"
  | "docs"
  | "security"
  | "performance"
  | "other";

export type EngineeringRequestStatus =
  | "submitted"
  | "analyzing"
  | "plan_ready"
  | "approved"
  | "rejected"
  | "in_progress"
  | "pr_opened"
  | "completed"
  | "failed";

export type EngineeringRequestPriority = "low" | "medium" | "high" | "urgent";

export type AffectedFile = {
  path: string;
  reason?: string;
};

export type EngineeringSafetyNotes = {
  allowed?: string[];
  forbidden?: string[];
  notes?: string[];
  human_approval_required?: boolean;
  ai_available?: boolean;
  rejection_reason?: string;
  [key: string]: unknown;
};

export type EngineeringRequestListItem = {
  id: string;
  repository_id: string | null;
  repository_full_name: string | null;
  title: string;
  request_type: EngineeringRequestType;
  status: EngineeringRequestStatus;
  priority: EngineeringRequestPriority;
  risk_level: RiskLevel | null;
  created_at: string;
  updated_at: string;
};

export type EngineeringRequestDetail = EngineeringRequestListItem & {
  organization_id: string;
  created_by_user_id: string | null;
  description: string;
  ai_summary: string | null;
  affected_files: AffectedFile[];
  implementation_plan: string[];
  test_plan: string[];
  safety_notes: EngineeringSafetyNotes;
};

export type CreateEngineeringRequestPayload = {
  title: string;
  description: string;
  request_type: EngineeringRequestType;
  priority: EngineeringRequestPriority;
  repository_id?: string | null;
};

export type RepositoryDNA = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  languages: string[];
  frameworks: string[];
  package_managers: string[];
  databases: string[];
  queues: string[];
  testing_tools: string[];
  build_tools: string[];
  cicd: string[];
  docker: { present?: boolean; files?: string[]; [key: string]: unknown };
  security_tools: string[];
  important_files: string[];
  architecture_summary: string | null;
  dependency_summary: { manifests_detected?: string[]; note?: string; [key: string]: unknown };
  repository_health: { score?: number | null; status?: string; notes?: string[]; [key: string]: unknown };
  risk_notes: string[];
  created_at: string;
  updated_at: string;
};

export type CodeAffectedFile = {
  path: string;
  change_type: "modify" | "create" | "delete" | string;
  reason?: string;
};

export type CodeGenerationPreview = {
  id: string;
  organization_id: string;
  engineering_request_id: string;
  repository_id: string | null;
  summary: string | null;
  affected_files: CodeAffectedFile[];
  diff_preview: string | null;
  implementation_tasks: string[];
  estimated_changes: {
    files?: number;
    estimated_additions?: number;
    estimated_deletions?: number;
    note?: string;
    [key: string]: unknown;
  };
  documentation_updates: string[];
  tests_to_create: string[];
  ai_available: boolean;
  created_at: string;
  updated_at: string;
};

export type DraftCommit = {
  order: number;
  message: string;
  files: string[];
};

export type DraftPullRequest = {
  id: string;
  organization_id: string;
  engineering_request_id: string;
  repository_id: string | null;
  branch_name: string;
  base_branch: string | null;
  title: string;
  body: string | null;
  commit_plan: DraftCommit[];
  labels: string[];
  status: string;
  is_pushed: boolean;
  human_approval_required: boolean;
  created_at: string;
  updated_at: string;
};

export type ValidationCheck = {
  name: string;
  status: "passed" | "failed" | "skipped" | string;
  details?: string;
  attempt?: number;
};

export type ValidationRun = {
  id: string;
  organization_id: string;
  engineering_request_id: string;
  repository_id: string | null;
  draft_pull_request_id: string | null;
  status: "passed" | "failed" | string;
  attempts: number;
  max_attempts: number;
  checks: ValidationCheck[];
  auto_fixes_applied: Array<Record<string, unknown>>;
  report: {
    success?: boolean;
    passed?: string[];
    failed?: string[];
    summary?: string;
    draft_pull_request_created?: boolean;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
};

export type ExecutionSafetyStatus = "safe" | "needs_approval" | "blocked";

export type ExecutionTask = {
  order: number;
  title: string;
  detail?: string;
};

export type ExecutionSafetyFinding = {
  level: string;
  category: string;
  message: string;
  path?: string;
};

export type ExecutionPlan = {
  id: string;
  organization_id: string;
  engineering_request_id: string;
  repository_id: string | null;
  tasks: ExecutionTask[];
  estimated_files: string[];
  dependency_analysis: {
    touches_dependencies?: boolean;
    dependency_files?: string[];
    note?: string;
    [key: string]: unknown;
  };
  complexity: string;
  estimated_duration: string | null;
  rollback_strategy: string[];
  validation_checklist: string[];
  repository_context: Record<string, unknown>;
  safety_status: ExecutionSafetyStatus;
  safety_findings: ExecutionSafetyFinding[];
  branch_name: string | null;
  created_at: string;
  updated_at: string;
};
