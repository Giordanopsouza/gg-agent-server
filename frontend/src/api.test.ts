import { afterEach, describe, expect, it, vi } from "vitest";
import { taskApi } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("Task API contract", () => {
  it("sends repository-backed submissions with the runtime key", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "task-1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetch);

    await taskApi.create("secret", {
      prompt: "Improve docs",
      idempotency_key: "request-1",
      repository: "owner/repo",
      base_ref: "main",
    });

    expect(fetch).toHaveBeenCalledWith("/tasks", {
      method: "POST",
      body: JSON.stringify({ prompt: "Improve docs", idempotency_key: "request-1", repository: "owner/repo", base_ref: "main" }),
      headers: { "X-API-Key": "secret", "Content-Type": "application/json" },
    });
  });

  it("requests only events after the last durable cursor", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetch);

    await taskApi.events("secret", "task/1", 42);

    expect(fetch).toHaveBeenCalledWith("/tasks/task%2F1/events?after=42", {
      headers: { "X-API-Key": "secret" },
    });
  });

  it("shows validation details from the API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "base_ref is required with repository" }), { status: 422 })));
    await expect(taskApi.list("secret")).rejects.toThrow("422: base_ref is required with repository");
  });
});
