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
  github_pr_number: number | null;
  github_pr_url: string | null;
  already_exists?: boolean;
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

export type SetupIntent = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  languages: string[];
  frameworks: string[];
  package_manager: string | null;
  runtime_version: string | null;
  install_command: string | null;
  dev_command: string | null;
  prod_command: string | null;
  test_command: string | null;
  build_command: string | null;
  lint_command: string | null;
  env_vars: string[];
  ports: number[];
  databases: string[];
  caches: string[];
  queues: string[];
  external_services: string[];
  docker: { present?: boolean; files?: string[]; [key: string]: unknown };
  cicd_provider: string | null;
  health_check_endpoint: string | null;
  confidence_score: number;
  sources_analyzed: string[];
  notes: string[];
  created_at: string;
  updated_at: string;
};

export type EnvironmentSpecEnvVar = { name: string; required: boolean };

export type EnvironmentSpec = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  primary_language: string | null;
  runtime_name: string | null;
  runtime_version: string | null;
  package_manager: string | null;
  framework: string | null;
  install_command: string | null;
  dev_command: string | null;
  prod_command: string | null;
  build_command: string | null;
  test_command: string | null;
  lint_command: string | null;
  health_check_command: string | null;
  databases: string[];
  caches: string[];
  queues: string[];
  external_services: string[];
  app_ports: number[];
  service_ports: number[];
  health_check_endpoint: string | null;
  env_vars: EnvironmentSpecEnvVar[];
  missing_env_example: boolean;
  container_strategy: string;
  workspace_requirements: {
    cpu?: number;
    memory_mb?: number;
    disk_mb?: number;
    network_access?: boolean;
    persistent_volumes?: string[];
    [key: string]: unknown;
  };
  safety: Record<string, unknown>;
  confidence_score: number;
  assumptions: string[];
  missing_information: string[];
  warnings: string[];
  evidence?: InferenceEvidence[];
  created_at: string;
  updated_at: string;
};

export type InferenceEvidence = {
  field: string;
  value: unknown;
  source: string;
  detail: string;
};

export type WorkspaceBlueprint = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  language: string | null;
  runtime: string | null;
  runtime_version: string | null;
  package_manager: string | null;
  framework: string | null;
  workspace_structure: {
    project_root?: string;
    source_directories?: string[];
    test_directories?: string[];
    documentation_directories?: string[];
    configuration_directories?: string[];
    generated_directories?: string[];
    ignored_directories?: string[];
    [key: string]: unknown;
  };
  environment_files: Array<{ name: string; action: string; purpose: string; variable_names: string[]; entries?: string[] }>;
  docker_assets: Array<{ name: string; status: string; description: string; extensions?: string[] }>;
  ide_assets: Array<{ name: string; status: string; description: string; extensions?: string[] }>;
  startup_plan: {
    install_sequence?: string[];
    build_sequence?: string[];
    start_sequence?: string[];
    health_check_sequence?: string[];
    shutdown_sequence?: string[];
    note?: string;
    [key: string]: unknown;
  };
  workspace_resources: {
    cpu?: number;
    ram_mb?: number;
    disk_mb?: number;
    network_access?: boolean;
    volumes?: string[];
    services?: string[];
    [key: string]: unknown;
  };
  readiness_score: number;
  recommendations: string[];
  warnings: string[];
  safety: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkspaceProvisionPlan = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  language: string | null;
  runtime: string | null;
  runtime_version: string | null;
  package_manager: string | null;
  framework: string | null;
  workspace_directory: {
    workspace_root?: string;
    repository_location?: string;
    config_directory?: string;
    cache_directory?: string;
    logs_directory?: string;
    temp_directory?: string;
    note?: string;
    [key: string]: unknown;
  };
  environment_preparation: {
    env_template?: string[];
    generated_env_template?: string;
    runtime_config?: { runtime?: string | null; runtime_version?: string | null; [key: string]: unknown };
    runtime_version_files?: string[];
    package_manager_config?: { manager?: string | null; config_file?: string | null };
    has_env_example?: boolean;
    note?: string;
    [key: string]: unknown;
  };
  container_preparation: {
    docker_image_plan?: { status?: string; base_image?: string; note?: string };
    docker_compose_plan?: { status?: string; services?: string[]; note?: string };
    dev_container_plan?: { status?: string; file?: string };
    network_plan?: { isolated?: boolean; exposed_ports?: number[] };
    volume_plan?: { volumes?: string[]; workspace_mount?: string };
    note?: string;
    [key: string]: unknown;
  };
  dependency_plan: Array<{ command: string; status: string }>;
  startup_plan: Array<{ order: number; phase: string; actions: string[] }>;
  validation: Array<{ label: string; status: string; detail?: string; points?: number }>;
  readiness_score: number;
  recommendations: string[];
  warnings: string[];
  safety: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkspaceLaunch = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  status: "pending" | "launching" | "running" | "healthy" | "unhealthy" | "stopped" | "failed" | "expired" | string;
  runtime: string | null;
  image: string | null;
  start_command: string | null;
  container_id: string | null;
  published_url: string | null;
  port_mappings: Array<{ host: number; container: number }>;
  health_status: string | null;
  health_detail: string | null;
  logs_tail: string[];
  resource_limits: { cpu?: number; memory_mb?: number; pids_limit?: number; network?: string; [key: string]: unknown };
  ttl_seconds: number;
  started_at: string | null;
  expires_at: string | null;
  stopped_at: string | null;
  safety: Record<string, unknown>;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceInstanceStatus =
  | "pending"
  | "provisioning"
  | "installing"
  | "starting"
  | "running"
  | "failed"
  | "stopped"
  | "cancelled"
  | "crashed";

export type WorkspaceInstanceLog = { stream: string; message: string };
export type WorkspaceTimelineEvent = { event: string; at: string; detail: string | null };

export type WorkspaceMetrics = {
  total: number;
  by_status: Record<string, number>;
  average_launch_ms: number | null;
  average_install_ms: number | null;
  average_startup_ms: number | null;
  launched: number;
  failure_reasons: Array<{ reason: string; count: number }>;
};

export type WorkspaceInstance = {
  id: string;
  organization_id: string;
  repository_id: string;
  repository_full_name: string | null;
  scan_id: string | null;
  environment_spec_id: string | null;
  blueprint_id: string | null;
  provision_id: string | null;
  status: WorkspaceInstanceStatus | string;
  runtime: string | null;
  workspace_path: string | null;
  install_command: string | null;
  runtime_command: string | null;
  preview_url: string | null;
  exposed_ports: number[];
  logs: WorkspaceInstanceLog[];
  events?: WorkspaceTimelineEvent[];
  error_message: string | null;
  last_heartbeat_at?: string | null;
  running_at?: string | null;
  cancel_requested?: boolean;
  recovery_attempts?: number;
  cpu_limit?: number | null;
  memory_limit_mb?: number | null;
  execution_timeout_seconds?: number;
  install_duration_ms?: number | null;
  startup_duration_ms?: number | null;
  launch_duration_ms?: number | null;
  stopped_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RoadmapPhase = { id: string; title: string; summary: string };
export type ProductBlocker = { type: string; severity: string; title: string; reason: string; reference_id: string };
export type ProductPriority = { title: string; rationale: string; category: string; score: number };

export type ProductBrainOverview = {
  roadmap: RoadmapPhase[];
  delivery: {
    repositories: number;
    engineering_requests: Record<string, number>;
    engineering_requests_total: number;
    workspaces: Record<string, number>;
    scans_total: number;
    high_risk_scans: number;
    [key: string]: unknown;
  };
  blockers: ProductBlocker[];
  priorities: ProductPriority[];
  summary: string;
};

export type BrainEvidence = { source: string; detail: string; reference: string | null };
export type BrainAction = { title: string; rationale: string; brain: string };

export type BrainStep = {
  id: string;
  brain: string;
  order: number;
  status: string;
  summary: string;
  confidence: number;
  evidence: BrainEvidence[];
  created_at: string;
};

export type BrainRun = {
  id: string;
  organization_id: string;
  conversation_id: string | null;
  question: string;
  status: string;
  primary_brain: string | null;
  brains_consulted: string[];
  confidence_score: number;
  answer: string | null;
  evidence: BrainEvidence[];
  suggested_actions: BrainAction[];
  created_at: string;
  updated_at: string;
  steps: BrainStep[];
};

export type BrainConversation = {
  id: string;
  organization_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type BrainMemory = {
  id: string;
  organization_id: string;
  kind: string;
  title: string;
  content: string;
  tags: string[];
  source: string | null;
  refs: unknown[];
  created_at: string;
  updated_at: string;
};

export type BrainDecision = {
  id: string;
  organization_id: string;
  run_id: string | null;
  title: string;
  decision: string;
  rationale: string | null;
  confidence: number;
  evidence: BrainEvidence[];
  created_at: string;
};

export type KnowledgeNode = {
  id: string;
  organization_id: string;
  node_type: string;
  title: string;
  summary: string;
  source_type: string | null;
  source_id: string | null;
  confidence_score: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type KnowledgeEdge = {
  id: string;
  from_node_id: string;
  to_node_id: string;
  relationship_type: string;
  confidence_score: number;
  evidence: unknown[];
  created_at: string;
};

export type KnowledgeNeighbor = {
  node: KnowledgeNode;
  edges: KnowledgeEdge[];
  neighbors: KnowledgeNode[];
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
