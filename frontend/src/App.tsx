import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authApi, configuredApiUrl, setSessionExpiredHandler, taskApi, type Branch, type CredentialStatus, type GitHubStatus, type Models, type Repository, type Session, type TaskEventCopy, type TaskRecord, type TaskResult } from "./api";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const draftKey = (userId: string) => `gg.task-draft.${userId}`;

function loginMessage(): string {
  const url = new URL(window.location.href);
  const outcome = url.searchParams.get("auth");
  const message = outcome === "cancelled" ? "Google sign-in was cancelled. You can try again."
    : outcome === "failed" ? "Google sign-in failed. Please try again." : "";
  return message;
}

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
  return task.state === "completed" ? task.agent_outcome || task.state : task.state;
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
  const prUrl = event.kind === "message" && payload.role === "assistant"
    ? body.match(/https:\/\/github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+\/pull\/\d+/)?.[0]
    : undefined;
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
        ) : <p className="event-body">{body || "No details"}{prUrl && <><br /><a href={prUrl} target="_blank" rel="noopener noreferrer">Open pull request ↗</a></>}</p>}
      </div>
    </article>
  );
}

function Detail({ id, onTask, onResult }: {
  id: string;
  onTask: (task: TaskRecord) => void;
  onResult: (id: string, result: TaskResult) => void;
}) {
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [events, setEvents] = useState<TaskEventCopy[]>([]);
  const [result, setResult] = useState<TaskResult | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [messageId, setMessageId] = useState(() => crypto.randomUUID());

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;
    let resultRevision: string | null = null;
    setTask(null);
    setEvents([]);
    setResult(null);
    setError("");
    const poll = async () => {
      try {
        const recordPromise = taskApi.get(id).then((record) => {
          if (!active) return;
          setTask(record);
          onTask(record);
          return record;
        });
        const eventsPromise = taskApi.events(id, cursor).then((copies) => {
          if (!active || !copies.length) return;
          cursor = Math.max(cursor, ...copies.map((copy) => copy.cursor));
          setEvents((previous) => [...previous, ...copies]);
        });
        const resultPromise = recordPromise.then(async (record) => {
          if (!record) return;
          const revision = `${record.state}:${record.updated_at}`;
          if (revision === resultRevision) return;
          const outcome = await taskApi.result(id);
          if (!active) return;
          setResult(outcome);
          onResult(id, outcome);
          resultRevision = revision;
        });
        const settled = await Promise.allSettled([recordPromise, eventsPromise, resultPromise]);
        const failed = settled.find((entry) => entry.status === "rejected");
        if (failed?.status === "rejected") throw failed.reason;
        if (!active) return;
        setError("");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load task");
      } finally {
        if (active) timer = setTimeout(poll, 2500);
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [id, onTask, onResult]);

  const prUrl = result?.publication?.pr_url || result?.prior_pr_url;
  const displayStatus = task ? statusLabel(task, result || undefined) : "loading";
  async function sendFollowup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim() || sending) return;
    setSending(true); setError("");
    try {
      await taskApi.message(id, message.trim(), messageId);
      setMessage(""); setMessageId(crypto.randomUUID());
    } catch (cause) { setError(String(cause)); }
    finally { setSending(false); }
  }
  return (
    <main className="main detail-main">
      <div className="page-top"><a className="back-link" href="#/">← All tasks</a><span className="eyebrow">TASK DETAIL</span></div>
      {error ? <div className="alert" role="alert">{error}</div> : null}
      {task ? <>
        <header className="detail-header">
          <div><div className="task-kicker">TASK #{task.seq} <span>·</span> {formatDate(task.created_at)}</div><h1>{task.prompt}</h1></div>
          <StatusChip status={displayStatus} />
        </header>
        <div className="detail-meta"><span>{task.repository ? `${task.repository}@${task.base_ref}` : "Blank workspace"}</span><span className="meta-id">{task.id}</span></div>
        {task.state === "sleeping" && <p className="workspace-note">Workspace sleeping. Your next message will wake it.</p>}
        {result?.workspace_expired && <p className="workspace-note">Previous workspace files expired. Your next message starts a fresh checkout and Pi session; the conversation history remains here.</p>}
        {result?.workspace_expires_at && <p className="workspace-note">Workspace files available until {formatDate(result.workspace_expires_at)} after the last activity.</p>}
        {prUrl ? <a className="pr-link" href={prUrl} target="_blank" rel="noopener noreferrer">View draft pull request ↗</a> : null}
        <div className="section-label">ACTIVITY <span>{events.length} events</span></div>
        <section className="timeline" aria-label="Task activity">
          <article className="event-card event-prompt"><div className="event-marker" aria-hidden="true">↗</div><div className="event-content"><div className="event-heading"><strong>You</strong><time dateTime={task.created_at}>{formatDate(task.created_at)}</time></div><p className="event-body">{task.prompt}</p></div></article>
          {events.map((copy) => <EventCard key={copy.cursor} copy={copy} />)}
          {!TERMINAL.has(task.state) && <div className="waiting"><span className="pulse" />Waiting for new activity…</div>}
        </section>
        {TERMINAL.has(task.state) && <section className={`outcome ${task.state === "failed" ? "outcome-failed" : ""}`}><div className="eyebrow">TASK OUTCOME</div><h2>{displayStatus.replaceAll("_", " ")}</h2><p>{result?.outcome_detail || task.outcome_detail || (task.state === "completed" ? "Task finished." : "Task ended.")}</p></section>}
        {!TERMINAL.has(task.state) && <form className="composer followup-composer" onSubmit={(event) => void sendFollowup(event)}><label htmlFor="followup">Continue the conversation</label><textarea id="followup" value={message} onChange={(event) => { setMessage(event.target.value); setMessageId(crypto.randomUUID()); }} rows={3} maxLength={16000} placeholder="Ask the agent to continue, commit, push, or open a PR…" /><button className="spawn-button" type="submit" disabled={sending || !message.trim()}>{sending ? "Sending…" : "Send message ↗"}</button></form>}
      </> : !error ? <div className="empty-panel">Loading task…</div> : null}
    </main>
  );
}

function Home({ userId, credential, github, onCreated }: { userId: string; credential: CredentialStatus | null; github: GitHubStatus | null; onCreated: (task: TaskRecord) => void }) {
  const [prompt, setPrompt] = useState(() => sessionStorage.getItem(draftKey(userId)) || "");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<Models | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repository, setRepository] = useState("");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [baseRef, setBaseRef] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submissionKey, setSubmissionKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    let active = true;
    void taskApi.models().then((value) => { if (active) { setModels(value); setModel(value.default); } }).catch((cause) => { if (active) setError(String(cause)); });
    return () => { active = false; };
  }, []);
  const refreshRepositories = useCallback(async () => {
    try { setError(""); setRepositories(await taskApi.repositories()); }
    catch (cause) { setRepositories([]); setError(String(cause)); }
  }, []);
  useEffect(() => {
    if (github?.status === "connected") void refreshRepositories();
    else { setRepositories([]); setRepository(""); }
  }, [github?.status, refreshRepositories]);
  useEffect(() => {
    setBranches([]); setBaseRef("");
    if (!repository) return;
    let active = true;
    void taskApi.branches(repository).then((items) => {
      if (active) {
        setBranches(items);
        const preferred = repositories.find((item) => item.full_name === repository)?.default_branch;
        setBaseRef(items.find((item) => item.name === preferred)?.name || items[0]?.name || "");
      }
    }).catch((cause) => { if (active) setError(String(cause)); });
    return () => { active = false; };
  }, [repository, repositories]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim() || !model || !credential?.configured || (repository && !baseRef)) return;
    setSubmitting(true); setError("");
    try {
      const task = await taskApi.create({ prompt: prompt.trim(), model, idempotency_key: submissionKey, ...(repository ? { repository, base_ref: baseRef } : {}) });
      sessionStorage.removeItem(draftKey(userId));
      setSubmissionKey(crypto.randomUUID());
      onCreated(task);
      window.location.hash = `#/tasks/${encodeURIComponent(task.id)}`;
    } catch (cause) { setError(String(cause)); }
    finally { setSubmitting(false); }
  }
  return <main className="main home-main"><div className="home-intro"><div className="eyebrow">YOUR WORKSPACE</div><h1>What should the agent do?</h1><p>Choose a model and, optionally, an authorized repository.</p></div>
    <form className="composer" onSubmit={(event) => void submit(event)}>
      <label className="field-label" htmlFor="prompt">TASK PROMPT <span>REQUIRED</span></label>
      <textarea id="prompt" value={prompt} onChange={(event) => { setPrompt(event.target.value); sessionStorage.setItem(draftKey(userId), event.target.value); setSubmissionKey(crypto.randomUUID()); }} placeholder="Describe what you want the agent to work on…" maxLength={16000} rows={6} />
      <div className="composer-divider" />
      <div className="repo-fields"><label>Model<select value={model} onChange={(event) => { setModel(event.target.value); setSubmissionKey(crypto.randomUUID()); }} disabled={!models}>{models?.models.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
      <div className="repo-heading"><div><strong>Repository</strong><p>Optional. Leave blank for a fresh workspace.</p></div><button type="button" className="text-button" onClick={() => void refreshRepositories()} disabled={github?.status !== "connected"}>Refresh</button></div>
      <div className="repo-fields"><label>GitHub repository<select value={repository} onChange={(event) => { setRepository(event.target.value); setSubmissionKey(crypto.randomUUID()); }} disabled={github?.status !== "connected"}><option value="">Blank workspace</option>{repositories.map((item) => <option key={item.id} value={item.full_name}>{item.full_name}{item.private ? " (private)" : ""}</option>)}</select></label>
      <label>Base branch<select value={baseRef} onChange={(event) => { setBaseRef(event.target.value); setSubmissionKey(crypto.randomUUID()); }} disabled={!repository || !branches.length}><option value="">Select a branch</option>{branches.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label></div>
      {error && <div className="alert" role="alert">{error}</div>}
      <div className="composer-footer"><span>One task, one workspace</span><button className="spawn-button" type="submit" disabled={submitting || !credential?.configured || !models || !prompt.trim() || (!!repository && !baseRef)}>{submitting ? "Spawning…" : "Spawn task"}<span aria-hidden="true">↗</span></button></div>
    </form><div className="home-note">Your agent works in the background. You can come back later.</div></main>;
}

function AccountSetup({ session, credential, github, onCredential, onGitHub, onLogout }: { session: Session; credential: CredentialStatus | null; github: GitHubStatus | null; onCredential: (value: CredentialStatus) => void; onGitHub: (value: GitHubStatus) => void; onLogout: () => void }) {
  const [keyDraft, setKeyDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(operation: () => Promise<void>) {
    setBusy(true); setError("");
    try { await operation(); } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  return <div className="account-setup"><div className="account-heading"><strong>{session.user.email || session.user.id}</strong><button type="button" className="text-button" onClick={onLogout}>Sign out</button></div>
    <div className="setup-group"><strong>OpenRouter</strong><span>{credential?.configured ? `Saved ${credential.mask || ""}` : "No key saved"}</span><div className="setup-actions"><input type="password" aria-label="OpenRouter key" autoComplete="off" placeholder="OpenRouter API key" value={keyDraft} onChange={(event) => setKeyDraft(event.target.value)} /><button type="button" disabled={busy || !keyDraft} onClick={() => void act(async () => { onCredential(await authApi.saveCredential(keyDraft)); setKeyDraft(""); })}>Save</button></div>{credential?.configured && <button type="button" className="text-button" disabled={busy} onClick={() => void act(async () => onCredential(await authApi.removeCredential()))}>Remove key</button>}</div>
    <div className="setup-group"><strong>GitHub</strong><span>{github?.status === "connected" ? `Connected as ${github.login}` : github?.status || "GitHub App setup pending"}</span><div className="setup-actions">{github && <a className="setup-link" href={authApi.githubUrl()}>{github.status === "connected" ? "Reconnect" : "Connect GitHub"}</a>}{github && github.status !== "disconnected" && <button type="button" className="text-button" disabled={busy} onClick={() => void act(async () => onGitHub(await authApi.disconnectGitHub()))}>Disconnect</button>}</div>{github?.status === "pending" && <small>GitHub App installation is pending approval.</small>}{github?.status === "connected" && <small>{github.installations.length} installation(s)</small>}</div>
    {error && <div className="alert" role="alert">{error}</div>}<small title={configuredApiUrl}>API: {configuredApiUrl}</small></div>;
}

export default function App() {
  const taskId = useTaskId();
  const [session, setSession] = useState<Session | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState(loginMessage);
  const [credential, setCredential] = useState<CredentialStatus | null>(null);
  const [github, setGitHub] = useState<GitHubStatus | null>(null);
  const [setupError, setSetupError] = useState("");
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [results, setResults] = useState<Record<string, TaskResult>>({});
  const [listError, setListError] = useState("");
  const [loadingTasks, setLoadingTasks] = useState(true);
  const onTask = useCallback((task: TaskRecord) => setTasks((previous) => [task, ...previous.filter((item) => item.id !== task.id)].sort((a, b) => b.seq - a.seq)), []);
  const onResult = useCallback((id: string, result: TaskResult) => setResults((previous) => ({ ...previous, [id]: result })), []);
  useEffect(() => { localStorage.removeItem("gg.runtime.apiKey"); }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("auth")) {
      url.searchParams.delete("auth");
      window.history.replaceState(null, "", url);
    }
  }, []);
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setSession(null); setCredential(null); setGitHub(null); setTasks([]); setResults({});
      setSetupError(""); setListError("");
      setSessionError("Your session expired. Sign in again to continue.");
    });
    return () => setSessionExpiredHandler(null);
  }, []);
  useEffect(() => {
    let active = true;
    void authApi.session().then((value) => { if (active) setSession(value); }).catch((cause) => {
      if (active && !(cause instanceof Error && cause.message.startsWith("401:"))) {
        setSessionError((previous) => previous || "Could not check your session. Please refresh and try again.");
      }
    }).finally(() => { if (active) setCheckingSession(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!session) return;
    let active = true;
    void Promise.allSettled([authApi.credential(), authApi.github()]).then(([key, connection]) => {
      if (!active) return;
      if (key.status === "fulfilled") setCredential(key.value);
      if (connection.status === "fulfilled") setGitHub(connection.value);
      const errors = [key, connection].filter((item) => item.status === "rejected" && !(item.reason instanceof Error && item.reason.message.startsWith("503: GitHub connection unavailable")));
      if (errors.length) setSetupError(errors.map((item) => item.status === "rejected" ? String(item.reason) : "").join("; "));
    });
    return () => { active = false; };
  }, [session]);
  useEffect(() => {
    if (!session) { setTasks([]); setResults({}); setLoadingTasks(true); return; }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const listed = await taskApi.list();
        if (!active) return;
        const recent = [...listed].sort((a, b) => b.seq - a.seq);
        setTasks(recent); setListError("");
      } catch (cause) { if (active) setListError(String(cause)); }
      finally { if (active) { setLoadingTasks(false); timer = setTimeout(poll, 5000); } }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [session]);
  async function logout() {
    try { await authApi.logout(); sessionStorage.removeItem(draftKey(session!.user.id)); setSession(null); setCredential(null); setGitHub(null); setTasks([]); setResults({}); setSessionError(""); setSetupError(""); setListError(""); window.location.hash = "#/"; }
    catch (cause) { setSetupError(String(cause)); }
  }
  if (checkingSession) return <main className="auth-screen"><div className="auth-card">Checking session…</div></main>;
  if (!session) return <main className="auth-screen"><div className="auth-card"><div className="brand-mark">gg</div><h1>gg / tasks</h1><p>Sign in to configure your account and run tasks.</p>{sessionError && <div className="alert" role="alert">{sessionError}</div>}<a className="spawn-button" href={authApi.loginUrl()}>Continue with Google ↗</a></div></main>;
  const groups = tasks.reduce((grouped, task) => {
    const repository = task.repository || "Blank workspace";
    if (!grouped.has(repository)) grouped.set(repository, []);
    grouped.get(repository)!.push(task);
    return grouped;
  }, new Map<string, TaskRecord[]>());
  return <div className="shell"><aside className="sidebar"><a className="brand" href="#/"><span className="brand-mark">g<span>g</span></span><span>gg<span className="brand-light"> / tasks</span></span></a>
    <div className="sidebar-heading"><span>WORKSPACE</span><a href="#/" className="new-link" aria-label="New task">+</a></div><a className={`nav-item ${!taskId ? "selected" : ""}`} href="#/"><span className="nav-icon">◫</span> Overview</a>
    <div className="sidebar-heading recent-heading"><span>HISTORY</span><span>{tasks.length}</span></div><nav className="task-nav" aria-label="Task history">{loadingTasks ? <p className="no-tasks" role="status">Loading history…</p> : listError ? <p className="sidebar-error" role="alert">Could not load history. Retrying…</p> : !tasks.length ? <p className="no-tasks">No tasks yet.</p> : [...groups].map(([repository, items]) => <section className="history-group" key={repository} aria-label={repository}><h2>{repository}</h2>{items.map((task) => <a className={`task-nav-item ${taskId === task.id ? "selected" : ""}`} href={`#/tasks/${encodeURIComponent(task.id)}`} key={task.id} aria-current={taskId === task.id ? "page" : undefined}><span className="nav-prompt">{task.prompt}</span><span className="history-meta"><StatusChip status={statusLabel(task, results[task.id])} /><time dateTime={task.created_at}>{formatDate(task.created_at)}</time></span></a>)}</section>)}</nav>
    <AccountSetup key={session.user.id} session={session} credential={credential} github={github} onCredential={setCredential} onGitHub={setGitHub} onLogout={() => void logout()} /></aside>
    <div className="content"><div className="topbar"><span>AGENT CONTROL PLANE</span><span className="topbar-right"><span className="online-dot" />Signed in</span></div>{setupError && <div className="alert setup-error" role="alert">{setupError}</div>}{taskId ? <Detail key={`${session.user.id}:${taskId}`} id={taskId} onTask={onTask} onResult={onResult} /> : <Home key={session.user.id} userId={session.user.id} credential={credential} github={github} onCreated={onTask} />}</div></div>;
}
