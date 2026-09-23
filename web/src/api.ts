export type TaskState =
  | "queued"
  | "starting"
  | "running"
  | "finalizing"
  | "completed"
  | "failed"
  | "cancelled";

export interface TaskRecord {
  id: string;
  seq: number;
  state: TaskState;
  prompt: string;
  repository: string | null;
  base_ref: string | null;
  created_at: string;
  updated_at: string;
  outcome_detail: string | null;
  check_status: string | null;
}

export interface TaskEventCopy {
  cursor: number;
  event: {
    id: string;
    kind: "message" | "action" | "observation" | "status" | "error";
    payload: Record<string, unknown>;
    created_at: string;
  };
}

export interface TaskResult {
  state: TaskState;
  outcome_detail: string | null;
  check_status: string | null;
  evidence_detail: string | null;
  manifest: {
    agent_outcome: string;
    check_outcome: string;
  } | null;
  publication: {
    state: string;
    pr_url: string | null;
    detail: string | null;
  } | null;
  prior_pr_url: string | null;
}

const baseUrl = (import.meta.env.VITE_TASK_API_URL || "").replace(/\/$/, "");

async function request<T>(path: string, apiKey: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "X-API-Key": apiKey,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === "string" ? error.detail : response.statusText;
    throw new Error(`${response.status}: ${detail || "Request failed"}`);
  }
  return response.json() as Promise<T>;
}

export const taskApi = {
  list: (key: string) => request<TaskRecord[]>("/tasks", key),
  get: (key: string, id: string) => request<TaskRecord>(`/tasks/${encodeURIComponent(id)}`, key),
  events: (key: string, id: string, after: number) =>
    request<TaskEventCopy[]>(`/tasks/${encodeURIComponent(id)}/events?after=${after}`, key),
  result: (key: string, id: string) =>
    request<TaskResult>(`/tasks/${encodeURIComponent(id)}/result`, key),
  create: (key: string, payload: {
    prompt: string;
    idempotency_key: string;
    repository?: string;
    base_ref?: string;
  }) => request<TaskRecord>("/tasks", key, { method: "POST", body: JSON.stringify(payload) }),
};

export const configuredApiUrl = baseUrl || "Same origin (Vite proxy in development)";
