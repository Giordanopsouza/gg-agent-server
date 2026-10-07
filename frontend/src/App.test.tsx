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
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
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
    const signOut = host.querySelector<HTMLButtonElement>('button[aria-label="Sign out"]')!;
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

async function navigate(hash: string) {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
}

async function enterText(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  await act(async () => {
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function workspaceFetch(configured = true) {
  const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
    url === "/auth/session" ? response({ user: { id: "user-a", email: "a@example.com" } })
      : url === "/auth/openrouter-credential" ? response({ configured })
        : url === "/auth/github" ? response({ status: "connected", installations: [], login: "owner" })
          : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a", "model-b"] })
            : url === "/tasks/repositories" ? response([{ id: 1, full_name: "owner/repo", default_branch: "main", private: false }])
              : url.endsWith("/branches") ? response([{ name: "main", sha: "abc" }])
                : url === "/tasks" ? init?.method === "POST" ? response(task("task-3", "owner/repo")) : response([task("task-1", "owner/repo"), task("task-2", null)])
                  : url === "/tasks/task-3" ? response(task("task-3", "owner/repo"))
                    : url.endsWith("/result") ? response({ state: "running", manifest: null })
                      : response([]),
  ));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("workspace interface", () => {
  it("searches task history and expands or collapses workspace groups", async () => {
    workspaceFetch();
    await renderApp();
    const group = host.querySelector<HTMLButtonElement>('.history-group[aria-label="owner/repo"] button')!;
    await act(async () => group.click());
    expect(group.getAttribute("aria-expanded")).toBe("false");
    expect(host.querySelector('a[href="#/tasks/task-1"]')).toBeNull();
    await act(async () => group.click());
    await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Search tasks"]')!.click());
    await enterText(host.querySelector<HTMLInputElement>('input[aria-label="Search task history"]')!, "task-2");
    expect(host.querySelector('nav[aria-label="Task history"]')?.textContent).toContain("Task task-2");
    expect(host.querySelector('nav[aria-label="Task history"]')?.textContent).not.toContain("Task task-1");
    await enterText(host.querySelector<HTMLInputElement>('input[aria-label="Search task history"]')!, "missing");
    expect(host.textContent).toContain("No matching tasks.");
  });

  it("keeps the draft when moving between Home, Tasks, and Settings", async () => {
    workspaceFetch();
    await renderApp();
    await enterText(host.querySelector<HTMLTextAreaElement>("#prompt")!, "Finish this later");
    await navigate("#/settings");
    expect(host.querySelector(".settings-main")?.textContent).toContain("OpenRouter");
    expect(host.querySelector(".settings-main")?.textContent).toContain("GitHub");
    await navigate("#/tasks");
    expect(host.querySelectorAll(".task-row")).toHaveLength(2);
    await navigate("#/");
    expect(host.querySelector<HTMLTextAreaElement>("#prompt")!.value).toBe("Finish this later");
  });

  it("submits the selected repository, branch, and model with the keyboard shortcut", async () => {
    const fetch = workspaceFetch();
    await renderApp();
    await enterText(host.querySelector<HTMLTextAreaElement>("#prompt")!, "Build a small tool");
    await act(async () => {
      const select = host.querySelector<HTMLSelectElement>(".repository-control select")!;
      select.value = "owner/repo";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      const model = host.querySelector<HTMLSelectElement>(".model-control select")!;
      model.value = "model-b";
      model.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(host.querySelector<HTMLSelectElement>(".branch-control select")!.value).toBe("main");
    await act(async () => host.querySelector<HTMLTextAreaElement>("#prompt")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true })));
    const submitted = fetch.mock.calls.find(([url, init]) => url === "/tasks" && init?.method === "POST")!;
    expect(JSON.parse(submitted[1]!.body as string)).toMatchObject({ prompt: "Build a small tool", repository: "owner/repo", base_ref: "main", model: "model-b" });
    expect(sessionStorage.getItem("gg.task-draft.user-a")).toBeNull();
    expect(window.location.hash).toBe("#/tasks/task-3");
    await navigate(window.location.hash);
    expect(host.querySelector(".detail-header h1")?.textContent).toBe("Task task-3");
  });

  it("blocks keyboard submission until a credential is configured", async () => {
    const fetch = workspaceFetch(false);
    await renderApp();
    await enterText(host.querySelector<HTMLTextAreaElement>("#prompt")!, "Build a small tool");
    expect(host.querySelector<HTMLButtonElement>(".send-button")!.disabled).toBe(true);
    await act(async () => host.querySelector<HTMLTextAreaElement>("#prompt")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: true, bubbles: true })));
    expect(fetch.mock.calls.filter(([url, init]) => url === "/tasks" && init?.method === "POST")).toHaveLength(0);
    expect(host.querySelector('.home-note a')?.getAttribute("href")).toBe("#/settings");
  });

  it("opens mobile navigation and closes it after selecting a page", async () => {
    vi.stubGlobal("innerWidth", 390);
    workspaceFetch();
    await renderApp();
    expect(host.querySelector(".shell")?.classList.contains("sidebar-closed")).toBe(true);
    await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Open sidebar"]')!.click());
    expect(host.querySelector(".shell")?.classList.contains("sidebar-open")).toBe(true);
    await act(async () => host.querySelector<HTMLAnchorElement>('.primary-nav a[href="#/settings"]')!.click());
    expect(host.querySelector(".shell")?.classList.contains("sidebar-closed")).toBe(true);
  });
});

describe("history and detail latency", () => {
  it("renders completed history with a single request per poll", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((url: string) => Promise.resolve(
      url === "/auth/session" ? response({ user: { id: "user-a", email: null } })
        : url === "/tasks" ? response([{ ...task("task-1", "owner/repo"), state: "completed", agent_outcome: "no_changes" }])
          : url === "/auth/openrouter-credential" ? response({ configured: false })
            : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
              : url === "/tasks/models" ? response({ default: "model-a", models: ["model-a"] })
                : response({}),
    ));
    vi.stubGlobal("fetch", fetch);
    try {
      await renderApp();
      expect(host.querySelector('nav[aria-label="Task history"]')?.textContent).toContain("no changes");
      expect(host.textContent).not.toContain("Loading history");
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(fetch.mock.calls.filter(([url]) => url === "/tasks")).toHaveLength(3);
      expect(fetch.mock.calls.filter(([url]) => url.endsWith("/result"))).toHaveLength(0);
    } finally { vi.useRealTimers(); }
  });

  it("shows detail before slow evidence and reuses unchanged results", async () => {
    vi.useFakeTimers();
    window.location.hash = "#/tasks/task-1";
    let finishResult!: (value: Response) => void;
    let finishEvents!: (value: Response) => void;
    let updated = "2026-09-29T10:00:00Z";
    const fetch = vi.fn((url: string) =>
      url === "/tasks/task-1/result" ? new Promise<Response>((resolve) => { finishResult = resolve; })
        : url.startsWith("/tasks/task-1/events") ? new Promise<Response>((resolve) => { finishEvents = resolve; })
          : Promise.resolve(url === "/auth/session" ? response({ user: { id: "user-a", email: null } })
            : url === "/tasks" ? response([task("task-1", null)])
              : url === "/tasks/task-1" ? response({ ...task("task-1", null), updated_at: updated })
                : url === "/auth/openrouter-credential" ? response({ configured: false })
                  : url === "/auth/github" ? response({ status: "disconnected", installations: [] })
                    : response({})),
    );
    vi.stubGlobal("fetch", fetch);
    try {
      await renderApp();
      expect(host.querySelector(".detail-header h1")?.textContent).toBe("Task task-1");
      await act(async () => { finishResult(response({ state: "running", manifest: null, publication: null })); finishEvents(response([])); });
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
      expect(fetch.mock.calls.filter(([url]) => url.endsWith("/result"))).toHaveLength(1);
      await act(async () => { finishEvents(response([])); });
      updated = "2026-09-29T10:01:00Z";
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
      expect(fetch.mock.calls.filter(([url]) => url.endsWith("/result"))).toHaveLength(2);
      await act(async () => { finishResult(response({ state: "running", manifest: null, publication: null })); finishEvents(response([])); });
    } finally { vi.useRealTimers(); }
  });
});
