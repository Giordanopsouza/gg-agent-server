import { useEffect, useRef, useState } from "react";
import { taskApi, type TaskEventCopy, type TaskRecord, type TaskResult } from "./api";

export interface TaskDetail {
  task: TaskRecord | null;
  events: TaskEventCopy[];
  result: TaskResult | null;
  cursor: number;
}
export interface TaskCache { details: Map<string, TaskDetail>; valid: boolean }

export function useTaskDetail(id: string, cache: TaskCache, onTask: (task: TaskRecord) => void, onResult: (id: string, result: TaskResult) => void) {
  const [detail, setDetail] = useState<TaskDetail>(() => cache.details.get(id) || { task: null, events: [], result: null, cursor: 0 });
  const [error, setError] = useState("");
  const refresh = useRef<() => void>(() => {});
  useEffect(() => {
    let active = true;
    const isActive = () => active && cache.valid;
    let current = cache.details.get(id) || { task: null, events: [], result: null, cursor: 0 };
    let socket: WebSocket | undefined;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let retry = 1000;
    const abort = new AbortController();
    const busy = new Set<string>();
    const again = new Set<string>();
    const save = (patch: Partial<TaskDetail>) => {
      if (!isActive()) return;
      current = { ...current, ...patch };
      cache.details.set(id, current);
      setDetail(current);
    };
    const merge = (copies: TaskEventCopy[]) => {
      if (!isActive() || !copies.length) return;
      // Replay and polling can overlap. Merge by cursor, never by arrival order.
      const events = new Map(current.events.map(copy => [copy.cursor, copy]));
      for (const copy of copies) events.set(copy.cursor, copy);
      let cursor = current.cursor;
      while (events.has(cursor + 1)) cursor += 1;
      save({ events: [...events.values()].sort((a, b) => a.cursor - b.cursor), cursor });
    };
    const load = async (kind: string, action: () => Promise<void>) => {
      if (!isActive()) return;
      if (busy.has(kind)) { again.add(kind); return; }
      busy.add(kind);
      try { await action(); }
      catch (cause) { if (isActive()) setError(String(cause)); }
      finally {
        busy.delete(kind);
        if (isActive() && again.delete(kind)) void load(kind, action);
      }
    };
    const metadata = () => {
      void load("task", async () => {
        const task = await taskApi.get(id, abort.signal);
        if (isActive()) { save({ task }); onTask(task); setError(""); }
      });
      void load("result", async () => {
        const result = await taskApi.result(id, abort.signal);
        if (isActive()) { save({ result }); onResult(id, result); }
      });
    };
    const connect = () => {
      if (!isActive() || typeof WebSocket === "undefined") return;
      let connection: WebSocket;
      try { connection = taskApi.eventSocket(id, current.cursor); socket = connection; }
      catch {
        reconnect = setTimeout(connect, retry);
        retry = Math.min(retry * 2, 15000);
        return;
      }
      connection.onopen = () => { if (isActive() && socket === connection) retry = 1000; };
      connection.onmessage = event => {
        if (!isActive() || socket !== connection) return;
        try {
          const copy = JSON.parse(event.data) as TaskEventCopy;
          if (!Number.isInteger(copy.cursor) || copy.cursor <= 0 || !copy.event) throw new Error("Invalid event");
          merge([copy]); metadata();
        }
        catch { connection.close(); }
      };
      connection.onclose = () => {
        if (!isActive() || socket !== connection) return;
        reconnect = setTimeout(connect, retry);
        retry = Math.min(retry * 2, 15000);
      };
      connection.onerror = () => connection.close();
    };
    const history = () => load("events", async () => {
      const copies = await taskApi.events(id, current.cursor, abort.signal);
      merge(copies);
    });
    const update = () => { metadata(); void history(); };
    refresh.current = update;
    metadata();
    // Load HTTP history first, then subscribe with its cursor. Server replay
    // covers events between these steps; polling also repairs dropped frames.
    void history().then(connect);
    const timer = setInterval(update, 2500);
    return () => {
      active = false; abort.abort(); clearInterval(timer); clearTimeout(reconnect);
      socket?.close(); refresh.current = () => {};
    };
  }, [id, cache, onTask, onResult]);
  return { ...detail, error, setError, refresh: () => refresh.current() };
}
