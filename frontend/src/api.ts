export type TaskState = "queued" | "starting" | "running" | "idle" | "sleeping" | "finalizing" | "completed" | "failed" | "cancelled";

export interface TaskRecord {
  id: string;
  seq: number;
  state: TaskState;
  prompt: string;
  repository: string | null;
  base_ref: string | null;
  model: string;
  created_at: string;
  updated_at: string;
  outcome_detail: string | null;
  check_status: string | null;
  workspace_expired: boolean;
  workspace_last_activity_at: string | null;
}

export interface TaskEventCopy {
  cursor: number;
  event: { id: string; kind: "message" | "action" | "observation" | "status" | "error"; payload: Record<string, unknown>; created_at: string };
}

export interface TaskResult {
  state: TaskState;
  outcome_detail: string | null;
  check_status: string | null;
  evidence_detail: string | null;
  manifest: { agent_outcome: string; check_outcome: string } | null;
  publication: { state: string; pr_url: string | null; detail: string | null } | null;
  prior_pr_url: string | null;
  workspace_available: boolean;
  workspace_expires_at: string | null;
  workspace_expired: boolean;
}

export interface Session { user: { id: string; email: string | null } }
export interface CredentialStatus { configured: boolean; mask: string | null; version: number | null }
export interface GitHubStatus { status: "connected" | "pending" | "disconnected" | "revoked"; login: string | null; installations: Array<{ id: number; account?: { login?: string } }> }
export interface Repository { id: number; full_name: string; private: boolean; default_branch: string; installation_id: number }
export interface Branch { name: string; sha: string }
export interface Models { default: string; models: string[] }

const baseUrl = (import.meta.env.VITE_TASK_API_URL || "").replace(/\/$/, "");
let onSessionExpired: (() => void) | null = null;

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    credentials: "include",
    signal: init?.signal || AbortSignal.timeout(10000),
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/session") onSessionExpired?.();
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === "string" ? error.detail : response.statusText;
    throw new Error(`${response.status}: ${detail || "Request failed"}`);
  }
  return response.json() as Promise<T>;
}

export const authApi = {
  session: () => request<Session>("/auth/session"),
  loginUrl: () => `${baseUrl}/auth/google/start?return_to=${encodeURIComponent("/")}`,
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  credential: () => request<CredentialStatus>("/auth/openrouter-credential"),
  saveCredential: (apiKey: string) => request<CredentialStatus>("/auth/openrouter-credential", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),
  removeCredential: () => request<CredentialStatus>("/auth/openrouter-credential", { method: "DELETE" }),
  github: () => request<GitHubStatus>("/auth/github"),
  githubUrl: () => `${baseUrl}/auth/github/start`,
  disconnectGitHub: () => request<GitHubStatus>("/auth/github", { method: "DELETE" }),
};

export const taskApi = {
  list: () => request<TaskRecord[]>("/tasks"),
  get: (id: string) => request<TaskRecord>(`/tasks/${encodeURIComponent(id)}`),
  events: (id: string, after: number) => request<TaskEventCopy[]>(`/tasks/${encodeURIComponent(id)}/events?after=${after}`),
  result: (id: string) => request<TaskResult>(`/tasks/${encodeURIComponent(id)}/result`),
  message: (id: string, content: string, messageId: string) =>
    request<{ id: string; status: string }>(`/tasks/${encodeURIComponent(id)}/messages`, {
      method: "POST", body: JSON.stringify({ id: messageId, content }),
    }),
  models: () => request<Models>("/tasks/models"),
  repositories: () => request<Repository[]>("/tasks/repositories"),
  branches: (repository: string) => request<Branch[]>(`/tasks/repositories/${encodeURIComponent(repository)}/branches`),
  create: (payload: { prompt: string; idempotency_key: string; model: string; repository?: string; base_ref?: string }) =>
    request<TaskRecord>("/tasks", { method: "POST", body: JSON.stringify(payload) }),
};

export const configuredApiUrl = baseUrl || "Same origin";
