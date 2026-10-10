// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { taskApi, type TaskEventCopy, type TaskRecord, type TaskResult } from "./api";
import { useTaskDetail, type TaskCache } from "./useTaskDetail";

const record = (id: string) => ({ id, prompt: id, state: "running" }) as TaskRecord;
const result = { state: "running" } as TaskResult;
const copy = (cursor: number): TaskEventCopy => ({ cursor, event: { id: `e${cursor}`, kind: "message", payload: { text: `message-${cursor}` }, created_at: "2026-10-09" } });
class Socket {
  static sockets: Socket[] = [];
  onopen?: () => void;
  onclose?: () => void;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  closed = false;
  constructor(public url: URL) { Socket.sockets.push(this); }
  close() { this.closed = true; this.onclose?.(); }
  emit(cursor: number) { this.onmessage?.({ data: JSON.stringify(copy(cursor)) }); }
}
let root: Root;
let host: HTMLDivElement;
let cache: TaskCache;
let refresh: () => void;
const onTask = vi.fn();
const onResult = vi.fn();
function Detail({ id }: { id: string }) {
  const value = useTaskDetail(id, cache, onTask, onResult);
  refresh = value.refresh;
  return <p>{value.task?.prompt}|{value.events.map(event => event.event.payload.text).join(",")}</p>;
}
async function show(id: string) { await act(async () => root.render(<Detail key={id} id={id} />)); }
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("WebSocket", Socket);
  Socket.sockets = [];
  host = document.createElement("div");
  root = createRoot(host);
  cache = { details: new Map(), valid: true };
  vi.spyOn(taskApi, "get").mockImplementation(async id => record(id));
  vi.spyOn(taskApi, "events").mockResolvedValue([copy(1)]);
  vi.spyOn(taskApi, "result").mockResolvedValue(result);
  onTask.mockClear(); onResult.mockClear();
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

it("shows cached history immediately, preserves cursor and ignores late responses from another task", async () => {
  await show("a");
  let finish!: (task: TaskRecord) => void;
  vi.mocked(taskApi.get).mockImplementation(id => id === "b" ? new Promise(resolve => { finish = resolve; }) : new Promise(() => {}));
  await show("b");
  await show("a");
  expect(host.textContent).toBe("a|message-1");
  expect(taskApi.events).toHaveBeenLastCalledWith("a", 1, expect.any(AbortSignal));
  await act(async () => finish(record("b-late")));
  expect(host.textContent).toBe("a|message-1");
  expect(onTask).not.toHaveBeenCalledWith(record("b-late"));
  expect(cache.details.get("b")?.task).toBeNull();
});

it("replays without duplicates, fills gaps by polling and reconnects from the contiguous cursor", async () => {
  await show("a");
  const socket = Socket.sockets[0];
  expect(socket.url.pathname).toBe("/tasks/sockets/events/a");
  expect(socket.url.search).toBe("?after=1");
  await act(async () => { socket.emit(1); socket.emit(3); });
  expect(cache.details.get("a")?.cursor).toBe(1);
  vi.mocked(taskApi.events).mockResolvedValue([copy(2), copy(3)]);
  await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
  expect(host.textContent).toBe("a|message-1,message-2,message-3");
  expect(cache.details.get("a")?.cursor).toBe(3);
  await act(async () => { socket.close(); await vi.advanceTimersByTimeAsync(1000); });
  expect(Socket.sockets[1].url.search).toBe("?after=3");
  await act(async () => { socket.emit(4); socket.onerror?.(); await vi.advanceTimersByTimeAsync(1000); });
  expect(cache.details.get("a")?.cursor).toBe(3);
  expect(Socket.sockets).toHaveLength(2);
  expect(Socket.sockets[1].closed).toBe(false);
});

it("refreshes immediately and keeps events moving while task metadata is slow", async () => {
  vi.mocked(taskApi.get).mockImplementation(() => new Promise(() => {}));
  await show("a");
  expect(taskApi.result).toHaveBeenCalledTimes(1);
  await act(async () => refresh());
  expect(taskApi.events).toHaveBeenCalledTimes(2);
  expect(taskApi.result).toHaveBeenCalledTimes(2);
  await act(async () => Socket.sockets[0].emit(2));
  expect(cache.details.get("a")?.events).toHaveLength(2);
  expect(taskApi.get).toHaveBeenCalledTimes(1);
});

it("falls back to polling when WebSocket is unavailable and cancels all work on unmount", async () => {
  vi.stubGlobal("WebSocket", undefined);
  await show("a");
  vi.mocked(taskApi.events).mockResolvedValue([copy(2)]);
  await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
  expect(cache.details.get("a")?.cursor).toBe(2);
  const signal = vi.mocked(taskApi.events).mock.calls[0][2]!;
  await act(async () => root.render(null));
  cache.valid = false; cache.details.clear();
  expect(signal.aborted).toBe(true);
  const calls = vi.mocked(taskApi.events).mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(taskApi.events).toHaveBeenCalledTimes(calls);
  expect(cache.details.size).toBe(0);
});

it("cannot refill an expired session cache even before React unmounts the detail", async () => {
  let finish!: (task: TaskRecord) => void;
  vi.mocked(taskApi.get).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await show("a");
  cache.valid = false;
  cache.details.clear();
  await act(async () => { finish(record("late private task")); Socket.sockets[0].emit(2); refresh(); });
  expect(cache.details.size).toBe(0);
  expect(onTask).not.toHaveBeenCalled();
  expect(host.textContent).not.toContain("late private task");
});
