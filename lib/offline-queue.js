export type QueuedOp = {
  id: string;
  path: string;
  method: string;
  body: unknown;
  label: string;
  ts: number;
  attempts: number;
};

const KEY = "hb.offqueue.v1";

function load(): QueuedOp[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]") as QueuedOp[]; }
  catch (_e) { return []; }
}
function persist(ops: QueuedOp[]) {
  try { localStorage.setItem(KEY, JSON.stringify(ops)); } catch (_e) { /* 存储满等忽略 */ }
}

let state: { online: boolean; ops: QueuedOp[] } | null = null;
let listeners = 0;
let flushTimer: number | undefined;

function notify() {
  if (!state) return;
  window.dispatchEvent(new CustomEvent("hb:offline-queue", { detail: state }));
}

async function flushOne(op: QueuedOp): Promise<boolean> {
  try {
    await $fetch(op.path, { method: op.method as any, body: op.body, retry: 0, headers: { "Idempotency-Key": op.id } });
    return true;
  } catch (e: any) {
    const st = e?.statusCode || e?.response?.status || 0;
    if (st && st < 500 && st !== 0) {
      console.warn("离线队列丢弃失败操作", op.path, st, op.label);
      return true;
    }
    return false;
  }
}

export function useOfflineQueue() {
  if (!import.meta.client) {
    return {
      enqueue: (_op: Omit<QueuedOp, "id" | "ts" | "attempts">) => {},
      flush: async () => {},
      pending: () => 0,
      ops: () => [] as QueuedOp[],
      isOffline: () => false,
    };
  }

  if (!state) {
    state = { online: navigator.onLine, ops: load() };
    window.addEventListener("online", () => {
      if (state) { state.online = true; notify(); void flushAll(); }
    });
    window.addEventListener("offline", () => {
      if (state) { state.online = false; notify(); }
    });
    flushTimer = window.setInterval(() => {
      if (state && state.online && state.ops.length) void flushAll();
    }, 30000);
  }

  async function flushAll() {
    if (!state) return;
    const q = state.ops;
    const remain: QueuedOp[] = [];
    let changed = false;
    for (const op of q) {
      const done = await flushOne(op);
      if (!done) {
        op.attempts++;
        if (op.attempts < 5) remain.push(op);
        changed = true;
      } else changed = true;
    }
    if (changed && state) {
      state.ops = remain;
      persist(remain);
      notify();
    }
  }

  function enqueue(op: Omit<QueuedOp, "ts" | "attempts"> & { id?: string }) {
    if (!state) return;
    state.ops.push({ ...op, id: op.id || Math.random().toString(36).slice(2), ts: Date.now(), attempts: 0 } as QueuedOp);
    persist(state.ops);
    notify();
    if (state.online) void flushAll();
  }

  void flushAll();

  return {
    enqueue,
    flush: () => flushAll(),
    pending: () => (state ? state.ops.length : 0),
    ops: () => (state ? [...state.ops] : []),
    isOffline: () => (state ? !state.online : false),
  };
}
