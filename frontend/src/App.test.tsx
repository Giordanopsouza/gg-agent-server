// @vitest-environment jsdom
import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const task = (id: string, repository: string | null) => ({
  id, seq: Number(id.slice(-1)), state: "running", prompt: `Task ${id}`,
  repository, base_ref: "main", model: "model-a", created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z", outcome_detail: null, check_status: null,
});

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let root: Root;
let host: HTMLDivElement;

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  window.history.replaceState(null, "", "/");
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

async function renderApp() {
  await act(async () => { root.render(<App />); });
}

describe("desktop session and history", () => {
  it("clears the account and draft after sign out", async () => {
    sessionStorage.setItem("gg.task-draft.user-a", "Unsent work");
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-a", email: "a@example.com" } })
        : url === "/auth/logout" ? response({ ok: true })
          : url === "/tasks" ? response([task("task-1", "owner/repo")])
            : url === "/auth/openrouter-credential" ? response({ configured: false })
              : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
                : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a"] })
                  : response([]),
    )));
    await renderApp();
    expect(host.textContent).toContain("a@example.com");
    const signOut = [...host.querySelectorAll("button")].find((item) => item.textContent === "Sign out")!;
    await act(async () => signOut.click());
    expect(host.textContent).toContain("Continue with Google");
    expect(host.textContent).not.toContain("a@example.com");
    expect(host.textContent).not.toContain("owner/repo");
    expect(sessionStorage.getItem("gg.task-draft.user-a")).toBeNull();
  });

  it("explains a failed Google sign-in", async () => {
    window.history.replaceState(null, "", "/?auth=failed");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ detail: "Unauthorized" }, 401))));
    await act(async () => { root.render(<StrictMode><App /></StrictMode>); });
    expect(host.textContent).toContain("Google sign-in failed. Please try again.");
    expect(window.location.search).toBe("");
  });

  it("groups history by repository and keeps a reloaded task selected", async () => {
    window.location.hash = "#/tasks/task-2";
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-a", email: "a@example.com" } })
        : url === "/tasks" ? response([task("task-1", "owner/repo"), task("task-2", null)])
          : url === "/tasks/task-2" ? response(task("task-2", null))
            : url === "/tasks/task-2/events?after=0" ? response([])
              : url === "/tasks/task-2/result" ? response({ state: "running", manifest: null, publication: null })
                : url === "/auth/openrouter-credential" ? response({ configured: false })
                  : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
                    : response({}),
    )));
    await renderApp();
    expect(host.querySelector('nav[aria-label="Task history"]')?.textContent).toContain("owner/repo");
    expect(host.querySelector('nav[aria-label="Task history"]')?.textContent).toContain("Blank workspace");
    expect(host.querySelector('a[aria-current="page"]')?.textContent).toContain("Task task-2");
    expect(host.querySelector(".detail-header h1")?.textContent).toBe("Task task-2");
  });

  it("hides account data on expiry and restores only that account's draft", async () => {
    sessionStorage.setItem("gg.task-draft.user-a", "Private draft");
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-a", email: "a@example.com" } })
        : url === "/tasks" ? response({ detail: "Session expired" }, 401)
          : url === "/auth/openrouter-credential" ? response({ configured: false })
            : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
              : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a"] })
                : response([]),
    )));
    await renderApp();
    expect(host.textContent).toContain("Your session expired");
    expect(host.textContent).not.toContain("a@example.com");
    expect(sessionStorage.getItem("gg.task-draft.user-a")).toBe("Private draft");
    await act(async () => root.unmount());
    root = createRoot(host);
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-b", email: "b@example.com" } })
        : url === "/tasks" ? response([])
          : url === "/auth/openrouter-credential" ? response({ configured: false })
            : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
              : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a"] })
                : response([]),
    )));
    await renderApp();
    expect((host.querySelector("#prompt") as HTMLTextAreaElement).value).toBe("");
    await act(async () => root.unmount());
    root = createRoot(host);
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-a", email: "a@example.com" } })
        : url === "/tasks" ? response([])
          : url === "/auth/openrouter-credential" ? response({ configured: false })
            : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
              : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a"] })
                : response([]),
    )));
    await renderApp();
    expect((host.querySelector("#prompt") as HTMLTextAreaElement).value).toBe("Private draft");
  });
});
