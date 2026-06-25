import type {
  ArchitectureRule,
  AuthResponse,
  CompanyRule,
  CreateEngineeringRequestPayload,
  DashboardResponse,
  DeadLetterScan,
  EngineeringRequestDetail,
  EngineeringRequestListItem,
  EngineeringRequestStatus,
  EngineeringRequestType,
  ExecutionPlan,
  HealthStatus,
  QueueMetrics,
  Repository,
  RepositoryDNA,
  RiskLevel,
  ScanDetail,
  ScanListItem,
  ScanStatus,
  User
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
