import { afterEach, describe, expect, it, vi } from "vitest";
import { authApi, taskApi } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("browser API contract", () => {
  it("submits the selected repository, branch, and model with the browser session", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "task-1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    await taskApi.create({ prompt: "Improve docs", idempotency_key: "request-1", model: "model-a", repository: "owner/repo", base_ref: "main" });
    expect(fetch).toHaveBeenCalledWith("/tasks", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ prompt: "Improve docs", idempotency_key: "request-1", model: "model-a", repository: "owner/repo", base_ref: "main" }),
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    }));
  });

  it("saves the OpenRouter key only in the request body", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ configured: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await authApi.saveCredential("test-secret");
    expect(fetch).toHaveBeenCalledWith("/auth/openrouter-credential", expect.objectContaining({
      method: "PUT", body: JSON.stringify({ api_key: "test-secret" }), credentials: "include", headers: { "Content-Type": "application/json" },
    }));
  });

  it("requests authorized branches and durable events", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("[]", { status: 200 })));
    vi.stubGlobal("fetch", fetch);
    await taskApi.branches("owner/repo");
    await taskApi.events("task/1", 42);
    expect(fetch).toHaveBeenNthCalledWith(1, "/tasks/repositories/owner%2Frepo/branches", expect.objectContaining({ credentials: "include", headers: {} }));
    expect(fetch).toHaveBeenNthCalledWith(2, "/tasks/task%2F1/events?after=42", expect.objectContaining({ credentials: "include", headers: {} }));
  });

  it("shows validation details from the API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "base_ref is required" }), { status: 422 })));
    await expect(taskApi.list()).rejects.toThrow("422: base_ref is required");
  });
});
