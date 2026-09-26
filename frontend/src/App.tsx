import { useCallback, useEffect, useState, type FormEvent } from "react";
import { configuredApiUrl, taskApi, type TaskEventCopy, type TaskRecord, type TaskResult } from "./api";

const KEY_STORAGE = "gg.runtime.apiKey";
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function currentTaskId(): string | null {
  const match = /^#\/tasks\/([^/]+)$/.exec(window.location.hash);
  return match ? decodeURIComponent(match[1]) : null;
}

function useTaskId(): string | null {
  const [id, setId] = useState(currentTaskId);
  useEffect(() => {
    const update = () => setId(currentTaskId());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return id;
}

function statusLabel(task: TaskRecord, result?: TaskResult): string {
  if (task.state === "completed" && result?.manifest?.agent_outcome) {
    return result.manifest.agent_outcome;
  }
  return task.state;
}

function StatusChip({ status }: { status: string }) {
  const tone = ["completed", "succeeded"].includes(status)
    ? "success"
    : status === "no_changes" ? "muted" : ["failed", "cancelled", "timeout"].includes(status)
      ? "failure" : "active";
  return <span className={`status-chip ${tone}`}><span className="status-dot" />{status.replaceAll("_", " ")}</span>;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function payloadText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
}

function EventCard({ copy }: { copy: TaskEventCopy }) {
  const { event } = copy;
  const { payload } = event;
  const tool = payloadText(payload.tool);
  const isTool = event.kind === "action" || event.kind === "observation";
  const title = event.kind === "message"
    ? (payload.role === "assistant" ? "Agent" : "Message")
    : event.kind === "action" ? `Using ${tool || "tool"}`
      : event.kind === "observation" ? `${tool || "Tool"} result`
        : event.kind === "error" ? "Error" : "Status update";
  const body = event.kind === "message" ? payloadText(payload.text ?? payload.content)
    : event.kind === "status" ? payloadText(payload.status)
      : event.kind === "error" ? payloadText(payload.message ?? payload.detail ?? payload)
        : payloadText(event.kind === "action" ? payload.args : payload.result);
  return (
    <article className={`event-card event-${event.kind}`}>
      <div className="event-marker" aria-hidden="true">{event.kind === "message" ? "✦" : event.kind === "error" ? "!" : isTool ? "›" : "•"}</div>
      <div className="event-content">
        <div className="event-heading"><strong>{title}</strong><time dateTime={event.created_at}>{formatDate(event.created_at)}</time></div>
        {isTool ? (
          <details className="tool-details" open={payload.is_error === true}>
            <summary>{event.kind === "action" ? "View tool input" : payload.is_error === true ? "Tool error" : "View tool output"}</summary>
            <pre>{body || "No details"}</pre>
          </details>
        ) : <p className="event-body">{body || "No details"}</p>}
      </div>
    </article>
  );
}

function Detail({ id, apiKey, onTask, onResult }: {
  id: string;
  apiKey: string;
  onTask: (task: TaskRecord) => void;
  onResult: (id: string, result: TaskResult) => void;
}) {
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [events, setEvents] = useState<TaskEventCopy[]>([]);
  const [result, setResult] = useState<TaskResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!apiKey) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;
    setTask(null);
    setEvents([]);
    setResult(null);
    setError("");
    const poll = async () => {
      try {
        const [record, copies, outcome] = await Promise.all([
          taskApi.get(apiKey, id), taskApi.events(apiKey, id, cursor), taskApi.result(apiKey, id),
        ]);
        if (!active) return;
        setTask(record);
        onTask(record);
        setResult(outcome);
        onResult(id, outcome);
        if (copies.length) {
          cursor = Math.max(cursor, ...copies.map((copy) => copy.cursor));
          setEvents((previous) => [...previous, ...copies]);
        }
        setError("");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load task");
      } finally {
        if (active) timer = setTimeout(poll, 2500);
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [apiKey, id, onTask, onResult]);

  const prUrl = result?.publication?.pr_url || result?.prior_pr_url;
  const displayStatus = task ? statusLabel(task, result || undefined) : "loading";
  return (
    <main className="main detail-main">
      <div className="page-top"><a className="back-link" href="#/">← All tasks</a><span className="eyebrow">TASK DETAIL</span></div>
      {!apiKey ? <div className="empty-panel">Save your Runtime API key to view this task.</div> : null}
      {error ? <div className="alert" role="alert">{error}</div> : null}
      {task ? <>
        <header className="detail-header">
          <div><div className="task-kicker">TASK #{task.seq} <span>·</span> {formatDate(task.created_at)}</div><h1>{task.prompt}</h1></div>
          <StatusChip status={displayStatus} />
        </header>
        <div className="detail-meta"><span>{task.repository ? `${task.repository}@${task.base_ref}` : "Blank workspace"}</span><span className="meta-id">{task.id}</span></div>
        {prUrl ? <a className="pr-link" href={prUrl} target="_blank" rel="noopener noreferrer">View draft pull request ↗</a> : null}
        <div className="section-label">ACTIVITY <span>{events.length} events</span></div>
        <section className="timeline" aria-label="Task activity">
          <article className="event-card event-prompt"><div className="event-marker" aria-hidden="true">↗</div><div className="event-content"><div className="event-heading"><strong>You</strong><time dateTime={task.created_at}>{formatDate(task.created_at)}</time></div><p className="event-body">{task.prompt}</p></div></article>
          {events.map((copy) => <EventCard key={copy.cursor} copy={copy} />)}
          {!TERMINAL.has(task.state) && <div className="waiting"><span className="pulse" />Waiting for new activity…</div>}
        </section>
        {TERMINAL.has(task.state) && <section className={`outcome ${task.state === "failed" ? "outcome-failed" : ""}`}><div className="eyebrow">TASK OUTCOME</div><h2>{displayStatus.replaceAll("_", " ")}</h2><p>{result?.outcome_detail || task.outcome_detail || (task.state === "completed" ? "Task finished." : "Task ended.")}</p>{result?.check_status && <span>Checks: {result.check_status}</span>}{result?.publication?.detail && <p>{result.publication.detail}</p>}</section>}
        <div className="disabled-composer"><span>↳</span><div><strong>Follow-up is unavailable in this version</strong><small>This task is read-only while it runs.</small></div></div>
      </> : apiKey && !error ? <div className="empty-panel">Loading task…</div> : null}
    </main>
  );
}

function Home({ apiKey, onCreated }: { apiKey: string; onCreated: (task: TaskRecord) => void }) {
  const [prompt, setPrompt] = useState("");
  const [repository, setRepository] = useState("");
  const [baseRef, setBaseRef] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!apiKey) { setError("Save your Runtime API key first."); return; }
    if (!prompt.trim()) { setError("Enter a task prompt."); return; }
    if (Boolean(repository.trim()) !== Boolean(baseRef.trim())) { setError("Enter both repository and base branch, or leave both empty."); return; }
    setSubmitting(true);
    setError("");
    try {
      const task = await taskApi.create(apiKey, {
        prompt: prompt.trim(),
        idempotency_key: crypto.randomUUID(),
        ...(repository.trim() ? { repository: repository.trim(), base_ref: baseRef.trim() } : {}),
      });
      onCreated(task);
      window.location.hash = `#/tasks/${encodeURIComponent(task.id)}`;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create task");
    } finally { setSubmitting(false); }
  }

  return <main className="main home-main">
    <div className="home-intro"><div className="eyebrow">YOUR WORKSPACE</div><h1>What should the agent do?</h1><p>Start a background task. Watch its progress here as it works.</p></div>
    <form className="composer" onSubmit={(event) => void submit(event)}>
      <label className="field-label" htmlFor="prompt">TASK PROMPT <span>REQUIRED</span></label>
      <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe what you want the agent to work on…" maxLength={16000} rows={6} />
      <div className="composer-divider" />
      <div className="repo-heading"><div><strong>Repository</strong><p>Optional. Leave blank for a fresh workspace.</p></div><span>OPTIONAL</span></div>
      <div className="repo-fields"><label>GitHub repository<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/name" autoComplete="off" /></label><label>Base branch<input value={baseRef} onChange={(event) => setBaseRef(event.target.value)} placeholder="main" autoComplete="off" /></label></div>
      {error && <div className="alert" role="alert">{error}</div>}
      <div className="composer-footer"><span>One task, one workspace</span><button className="spawn-button" type="submit" disabled={submitting}>{submitting ? "Spawning…" : "Spawn task"}<span aria-hidden="true">↗</span></button></div>
    </form>
    <div className="home-note"><span>✦</span> Your agent works in the background. You can close this tab and come back later.</div>
  </main>;
}

export default function App() {
  const taskId = useTaskId();
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(KEY_STORAGE) || "");
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [results, setResults] = useState<Record<string, TaskResult>>({});
  const [listError, setListError] = useState("");
  const onTask = useCallback((task: TaskRecord) => setTasks((previous) => [task, ...previous.filter((item) => item.id !== task.id)].sort((a, b) => b.seq - a.seq)), []);
  const onResult = useCallback((id: string, result: TaskResult) => setResults((previous) => ({ ...previous, [id]: result })), []);

  useEffect(() => {
    if (!apiKey) { setTasks([]); setResults({}); return; }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const listed = await taskApi.list(apiKey);
        if (!active) return;
        const recent = [...listed].sort((a, b) => b.seq - a.seq).slice(0, 12);
        setTasks(recent);
        setListError("");
        const finished = recent.filter((task) => TERMINAL.has(task.state));
        const settled = await Promise.allSettled(finished.map((task) => taskApi.result(apiKey, task.id)));
        if (active) setResults(Object.fromEntries(settled.flatMap((entry, index) => entry.status === "fulfilled" ? [[finished[index].id, entry.value] as const] : [])));
      } catch (cause) {
        if (active) setListError(cause instanceof Error ? cause.message : "Could not list tasks");
      } finally { if (active) timer = setTimeout(poll, 5000); }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [apiKey]);

  function saveKey() {
    const value = keyDraft.trim();
    if (value) localStorage.setItem(KEY_STORAGE, value);
    else localStorage.removeItem(KEY_STORAGE);
    setApiKey(value);
  }

  function clearKey() {
    localStorage.removeItem(KEY_STORAGE);
    setKeyDraft("");
    setApiKey("");
  }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#/"><span className="brand-mark">g<span>g</span></span><span>gg<span className="brand-light"> / tasks</span></span></a>
      <div className="sidebar-heading"><span>WORKSPACE</span><a href="#/" className="new-link" aria-label="New task">+</a></div>
      <a className={`nav-item ${!taskId ? "selected" : ""}`} href="#/"><span className="nav-icon">◫</span> Overview</a>
      <div className="sidebar-heading recent-heading"><span>RECENT TASKS</span><span>{tasks.length}</span></div>
      <nav className="task-nav" aria-label="Recent tasks">
        {tasks.map((task) => <a className={`task-nav-item ${taskId === task.id ? "selected" : ""}`} href={`#/tasks/${encodeURIComponent(task.id)}`} key={task.id}><span className="nav-prompt">{task.prompt}</span><StatusChip status={statusLabel(task, results[task.id])} /></a>)}
        {!tasks.length && <p className="no-tasks">{apiKey ? "No tasks yet." : "Save your API key to see tasks."}</p>}
      </nav>
      {listError && <p className="sidebar-error" role="alert">{listError}</p>}
      <div className="sidebar-bottom"><div className="connection"><span className="connection-dot" /> RUNTIME CONNECTION</div><label htmlFor="api-key">API key</label><div className="key-row"><input id="api-key" type="password" value={keyDraft} onChange={(event) => setKeyDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") saveKey(); }} placeholder="Enter API key" /><button type="button" onClick={saveKey}>Save</button></div>{apiKey && <button type="button" className="clear-key" onClick={clearKey}>Clear saved key</button>}<small title={configuredApiUrl}>API: {configuredApiUrl}</small></div>
    </aside>
    <div className="content"><div className="topbar"><span>AGENT CONTROL PLANE</span><span className="topbar-right"><span className={apiKey ? "online-dot" : "offline-dot"} />{apiKey ? "Connected key" : "Key required"}</span></div>{taskId ? <Detail key={taskId} id={taskId} apiKey={apiKey} onTask={onTask} onResult={onResult} /> : <Home apiKey={apiKey} onCreated={onTask} />}</div>
  </div>;
}
