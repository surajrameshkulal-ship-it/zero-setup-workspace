import type {
  ArchitectureRule,
  AuthResponse,
  BrainConversation,
  BrainDecision,
  BrainMemory,
  BrainRun,
  KnowledgeNeighbor,
  KnowledgeNode,
  CodeGenerationPreview,
  CompanyRule,
  CreateEngineeringRequestPayload,
  DashboardResponse,
  DeadLetterScan,
  DraftPullRequest,
  EngineeringRequestDetail,
  EnvironmentSpec,
  EngineeringRequestListItem,
  EngineeringRequestStatus,
  EngineeringRequestType,
  ExecutionPlan,
  HealthStatus,
  ProductBrainOverview,
  QueueMetrics,
  Repository,
  RepositoryDNA,
  RiskLevel,
  SetupIntent,
  ScanDetail,
  ScanListItem,
  ScanStatus,
  User,
  ValidationRun,
  WorkspaceBlueprint,
  WorkspaceInstance,
  WorkspaceLaunch,
  WorkspaceMetrics,
  WorkspaceProvisionPlan
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "codedna.access_token";

type RequestOptions = RequestInit & {
  token?: string | null;
};

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = options.token ?? getStoredToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (options.body && !headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    let details: unknown = null;
    try {
      details = await response.json();
    } catch {
      details = await response.text();
    }
    const message =
      typeof details === "object" &&
      details !== null &&
      "error" in details &&
      typeof details.error === "object" &&
      details.error !== null &&
      "message" in details.error
        ? String(details.error.message)
        : `Request failed with status ${response.status}`;
    throw new ApiError(response.status, message, details);
  }

  // No-content responses (e.g. 204 from DELETE) have no body to parse.
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  return apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
}

export function getMe(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export function getDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>("/dashboard");
}

export function getProductBrainOverview(): Promise<ProductBrainOverview> {
  return apiFetch<ProductBrainOverview>("/product-brain/overview");
}

// --- Phase 12.0: CodeDNA Super Brain ---

export function askBrain(question: string, conversationId?: string): Promise<BrainRun> {
  return apiFetch<BrainRun>("/brain/ask", {
    method: "POST",
    body: JSON.stringify({ question, conversation_id: conversationId ?? null })
  });
}

export function getBrainRun(runId: string): Promise<BrainRun> {
  return apiFetch<BrainRun>(`/brain/runs/${runId}`);
}

export function listBrainConversations(): Promise<BrainConversation[]> {
  return apiFetch<BrainConversation[]>("/brain/conversations");
}

export function listBrainMemory(query?: string): Promise<BrainMemory[]> {
  const q = query ? `?query=${encodeURIComponent(query)}` : "";
  return apiFetch<BrainMemory[]>(`/brain/memory${q}`);
}

export function listBrainDecisions(): Promise<BrainDecision[]> {
  return apiFetch<BrainDecision[]>("/brain/decisions");
}

// --- Phase 12.1: knowledge graph ---

export function ingestKnowledge(): Promise<{ nodes: number; edges: number }> {
  return apiFetch<{ nodes: number; edges: number }>("/brain/knowledge/ingest", { method: "POST" });
}

export function listKnowledgeNodes(nodeType?: string): Promise<KnowledgeNode[]> {
  const q = nodeType ? `?node_type=${encodeURIComponent(nodeType)}` : "";
  return apiFetch<KnowledgeNode[]>(`/brain/knowledge/nodes${q}`);
}

export function searchKnowledge(query: string): Promise<KnowledgeNode[]> {
  return apiFetch<KnowledgeNode[]>(`/brain/knowledge/search?query=${encodeURIComponent(query)}`);
}

export function listStaleKnowledge(): Promise<KnowledgeNode[]> {
  return apiFetch<KnowledgeNode[]>("/brain/knowledge/stale");
}

export function getKnowledgeGraph(nodeId: string): Promise<KnowledgeNeighbor> {
  return apiFetch<KnowledgeNeighbor>(`/brain/knowledge/graph?node_id=${nodeId}`);
}

export function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export function getQueueMetrics(): Promise<QueueMetrics> {
  return apiFetch<QueueMetrics>("/admin/queue-metrics");
}

export function listDeadLetterScans(): Promise<DeadLetterScan[]> {
  return apiFetch<DeadLetterScan[]>("/admin/dead-letter-scans");
}

export function listRepositories(): Promise<Repository[]> {
  return apiFetch<Repository[]>("/repositories");
}

export function generateRepositoryDna(repositoryId: string): Promise<RepositoryDNA> {
  return apiFetch<RepositoryDNA>(`/repositories/${repositoryId}/dna`, { method: "POST" });
}

export async function getRepositoryDna(repositoryId: string): Promise<RepositoryDNA | null> {
  try {
    return await apiFetch<RepositoryDNA>(`/repositories/${repositoryId}/dna`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function generateSetupIntent(repositoryId: string): Promise<SetupIntent> {
  return apiFetch<SetupIntent>(`/repositories/${repositoryId}/setup-intent`, { method: "POST" });
}

export async function getSetupIntent(repositoryId: string): Promise<SetupIntent | null> {
  try {
    return await apiFetch<SetupIntent>(`/repositories/${repositoryId}/setup-intent`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function generateEnvironmentSpec(repositoryId: string): Promise<EnvironmentSpec> {
  return apiFetch<EnvironmentSpec>(`/repositories/${repositoryId}/environment-spec`, { method: "POST" });
}

export async function getEnvironmentSpec(repositoryId: string): Promise<EnvironmentSpec | null> {
  try {
    return await apiFetch<EnvironmentSpec>(`/repositories/${repositoryId}/environment-spec`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function generateWorkspaceBlueprint(repositoryId: string): Promise<WorkspaceBlueprint> {
  return apiFetch<WorkspaceBlueprint>(`/repositories/${repositoryId}/workspace-blueprint`, { method: "POST" });
}

export async function getWorkspaceBlueprint(repositoryId: string): Promise<WorkspaceBlueprint | null> {
  try {
    return await apiFetch<WorkspaceBlueprint>(`/repositories/${repositoryId}/workspace-blueprint`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function generateWorkspaceProvision(repositoryId: string): Promise<WorkspaceProvisionPlan> {
  return apiFetch<WorkspaceProvisionPlan>(`/repositories/${repositoryId}/workspace-provision`, {
    method: "POST"
  });
}

export async function getWorkspaceProvision(repositoryId: string): Promise<WorkspaceProvisionPlan | null> {
  try {
    return await apiFetch<WorkspaceProvisionPlan>(`/repositories/${repositoryId}/workspace-provision`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function launchWorkspace(repositoryId: string): Promise<WorkspaceLaunch> {
  return apiFetch<WorkspaceLaunch>(`/repositories/${repositoryId}/workspace-launch`, { method: "POST" });
}

export function stopWorkspaceLaunch(repositoryId: string): Promise<WorkspaceLaunch> {
  return apiFetch<WorkspaceLaunch>(`/repositories/${repositoryId}/workspace-launch/stop`, { method: "POST" });
}

export async function getWorkspaceLaunch(repositoryId: string): Promise<WorkspaceLaunch | null> {
  try {
    return await apiFetch<WorkspaceLaunch>(`/repositories/${repositoryId}/workspace-launch`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

// --- Phase 11 Step 5: real sandbox lifecycle (WorkspaceInstance) ---

export function launchWorkspaceInstance(repositoryId: string): Promise<WorkspaceInstance> {
  return apiFetch<WorkspaceInstance>(`/workspaces/${repositoryId}/launch`, { method: "POST" });
}

export function listWorkspaceInstances(repositoryId: string): Promise<WorkspaceInstance[]> {
  return apiFetch<WorkspaceInstance[]>(`/workspaces?repository_id=${repositoryId}`);
}

export async function getLatestWorkspaceInstance(repositoryId: string): Promise<WorkspaceInstance | null> {
  const instances = await listWorkspaceInstances(repositoryId);
  return instances.length > 0 ? instances[0] : null;
}

export function getWorkspaceInstance(workspaceId: string): Promise<WorkspaceInstance> {
  return apiFetch<WorkspaceInstance>(`/workspaces/${workspaceId}`);
}

export function stopWorkspaceInstance(workspaceId: string): Promise<WorkspaceInstance> {
  return apiFetch<WorkspaceInstance>(`/workspaces/${workspaceId}/stop`, { method: "POST" });
}

export function restartWorkspaceInstance(workspaceId: string): Promise<WorkspaceInstance> {
  return apiFetch<WorkspaceInstance>(`/workspaces/${workspaceId}/restart`, { method: "POST" });
}

export function cancelWorkspaceInstance(workspaceId: string): Promise<WorkspaceInstance> {
  return apiFetch<WorkspaceInstance>(`/workspaces/${workspaceId}/cancel`, { method: "POST" });
}

export function getWorkspaceMetrics(repositoryId?: string): Promise<WorkspaceMetrics> {
  const q = repositoryId ? `?repository_id=${repositoryId}` : "";
  return apiFetch<WorkspaceMetrics>(`/workspaces/metrics${q}`);
}

export function deleteWorkspaceInstance(workspaceId: string): Promise<void> {
  return apiFetch<void>(`/workspaces/${workspaceId}`, { method: "DELETE" });
}

export function getRepository(repositoryId: string): Promise<Repository> {
  return apiFetch<Repository>(`/repositories/${repositoryId}`);
}

export function listScans(filters: {
  repository_id?: string;
  status?: ScanStatus | "";
  risk_level?: RiskLevel | "";
} = {}): Promise<ScanListItem[]> {
  const params = new URLSearchParams();
  if (filters.repository_id) {
    params.set("repository_id", filters.repository_id);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.risk_level) {
    params.set("risk_level", filters.risk_level);
  }
  const query = params.toString();
  return apiFetch<ScanListItem[]>(`/scans${query ? `?${query}` : ""}`);
}

export function getScan(scanId: string): Promise<ScanDetail> {
  return apiFetch<ScanDetail>(`/scans/${scanId}`);
}

export function listRepositoryScans(repositoryId: string): Promise<ScanListItem[]> {
  return apiFetch<ScanListItem[]>(`/repositories/${repositoryId}/scans`);
}

export function listCompanyRules(): Promise<CompanyRule[]> {
  return apiFetch<CompanyRule[]>("/rules/company");
}

export function listArchitectureRules(): Promise<ArchitectureRule[]> {
  return apiFetch<ArchitectureRule[]>("/rules/architecture");
}

export function createCompanyRule(payload: {
  name: string;
  description: string;
  rule_type: CompanyRule["rule_type"];
  pattern: string;
  severity: CompanyRule["severity"];
}): Promise<CompanyRule> {
  return apiFetch<CompanyRule>("/rules/company", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function createArchitectureRule(payload: {
  name: string;
  description: string;
  source_path_pattern: string;
  forbidden_import_pattern: string;
  severity: ArchitectureRule["severity"];
}): Promise<ArchitectureRule> {
  return apiFetch<ArchitectureRule>("/rules/architecture", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listEngineeringRequests(filters: {
  status?: EngineeringRequestStatus | "";
  request_type?: EngineeringRequestType | "";
  repository_id?: string;
} = {}): Promise<EngineeringRequestListItem[]> {
  const params = new URLSearchParams();
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.request_type) {
    params.set("request_type", filters.request_type);
  }
  if (filters.repository_id) {
    params.set("repository_id", filters.repository_id);
  }
  const query = params.toString();
  return apiFetch<EngineeringRequestListItem[]>(`/engineering-requests${query ? `?${query}` : ""}`);
}

export function getEngineeringRequest(requestId: string): Promise<EngineeringRequestDetail> {
  return apiFetch<EngineeringRequestDetail>(`/engineering-requests/${requestId}`);
}

export function createEngineeringRequest(
  payload: CreateEngineeringRequestPayload
): Promise<EngineeringRequestDetail> {
  return apiFetch<EngineeringRequestDetail>("/engineering-requests", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function analyzeEngineeringRequest(requestId: string): Promise<EngineeringRequestDetail> {
  return apiFetch<EngineeringRequestDetail>(`/engineering-requests/${requestId}/analyze`, {
    method: "POST"
  });
}

export function approveEngineeringRequestPlan(requestId: string): Promise<EngineeringRequestDetail> {
  return apiFetch<EngineeringRequestDetail>(`/engineering-requests/${requestId}/approve-plan`, {
    method: "POST"
  });
}

export function rejectEngineeringRequestPlan(
  requestId: string,
  reason?: string
): Promise<EngineeringRequestDetail> {
  return apiFetch<EngineeringRequestDetail>(`/engineering-requests/${requestId}/reject-plan`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null })
  });
}

export function generateExecutionPlan(requestId: string): Promise<ExecutionPlan> {
  return apiFetch<ExecutionPlan>(`/engineering-requests/${requestId}/execution-plan`, {
    method: "POST"
  });
}

export async function getExecutionPlan(requestId: string): Promise<ExecutionPlan | null> {
  try {
    return await apiFetch<ExecutionPlan>(`/engineering-requests/${requestId}/execution-plan`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function generateCodePreview(requestId: string): Promise<CodeGenerationPreview> {
  return apiFetch<CodeGenerationPreview>(`/engineering-requests/${requestId}/code-generation`, {
    method: "POST"
  });
}

export async function getCodePreview(requestId: string): Promise<CodeGenerationPreview | null> {
  try {
    return await apiFetch<CodeGenerationPreview>(`/engineering-requests/${requestId}/code-generation`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function prepareDraftPullRequest(requestId: string): Promise<DraftPullRequest> {
  return apiFetch<DraftPullRequest>(`/engineering-requests/${requestId}/draft-pr`, { method: "POST" });
}

export async function getDraftPullRequest(requestId: string): Promise<DraftPullRequest | null> {
  try {
    return await apiFetch<DraftPullRequest>(`/engineering-requests/${requestId}/draft-pr`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function createGithubDraftPullRequest(requestId: string): Promise<DraftPullRequest> {
  return apiFetch<DraftPullRequest>(`/engineering-requests/${requestId}/create-draft-pr`, {
    method: "POST"
  });
}

export function runValidation(requestId: string): Promise<ValidationRun> {
  return apiFetch<ValidationRun>(`/engineering-requests/${requestId}/validate`, { method: "POST" });
}

export async function getValidation(requestId: string): Promise<ValidationRun | null> {
  try {
    return await apiFetch<ValidationRun>(`/engineering-requests/${requestId}/validation`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}
