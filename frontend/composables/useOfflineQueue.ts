import { useViewPreferences } from "./use-preferences";
import { toast } from "@/components/ui/sonner";

export type QueuedOp = {
  id: string;
  path: string;
  method: string;
  body: unknown;
  label: string;
  ts: number;
  attempts: number;
  // 入队时的集合 ID；旧队列数据没有该字段，flush 时按当前集合处理
  tenant?: string;
};

const KEY = "hb.offqueue.v1";
const DEAD_KEY = "hb.offqueue.dead";
const DEAD_MAX = 50;

function load(): QueuedOp[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]") as QueuedOp[]; }
  catch (_e) { return []; }
}
function persist(ops: QueuedOp[]) {
  try { localStorage.setItem(KEY, JSON.stringify(ops)); } catch (_e) { /* 存储满等忽略 */ }
}

let state: { online: boolean; ops: QueuedOp[] } | null = null;
let flushTimer: number | undefined;
let flushing = false;

function notify() {
  if (!state) return;
  window.dispatchEvent(new CustomEvent("hb:offline-queue", { detail: state }));
}

function currentTenant(): string {
  try { return useViewPreferences().value.collectionId || ""; } catch (_e) { return ""; }
}

// 4xx 丢弃前留底：toast 提醒 + 死信键，便于排查丢单
function deadLetter(op: QueuedOp, status: number) {
  try {
    const dead = JSON.parse(localStorage.getItem(DEAD_KEY) || "[]") as Array<QueuedOp & { status: number; deadTs: number }>;
    dead.push({ ...op, status, deadTs: Date.now() });
    localStorage.setItem(DEAD_KEY, JSON.stringify(dead.slice(-DEAD_MAX)));
  } catch (_e) { /* 存储满等忽略 */ }
  try { void toast.warning(`离线操作被服务器拒绝（${status}），已丢弃：${op.label}`); } catch (_e) { /* ignore */ }
  console.warn("离线队列丢弃失败操作", op.path, status, op.label);
}

async function flushOne(op: QueuedOp): Promise<boolean> {
  try {
    const tenant = op.tenant || currentTenant();
    const headers: Record<string, string> = { "Idempotency-Key": op.id };
    if (tenant) headers["X-Tenant"] = tenant;
    await $fetch(op.path, { method: op.method as any, body: op.body, retry: 0, headers });
    return true;
  } catch (e: any) {
    const st = e?.statusCode || e?.response?.status || 0;
    if (st && st < 500) {
      deadLetter(op, st);
      return true;
    }
    return false;
  }
}

export function useOfflineQueue() {
  if (!import.meta.client) {
    return {
      enqueue: (_op: Omit<QueuedOp, "ts" | "attempts"> & { id?: string }) => {},
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
    // 四入口（enqueue 即时 / 30s 定时 / online 事件 / 页面挂载）会重叠触发，加锁防同一 op 重复提交
    if (!state || flushing) return;
    flushing = true;
    try {
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
    } finally {
      flushing = false;
    }
  }

  function enqueue(op: Omit<QueuedOp, "ts" | "attempts"> & { id?: string }) {
    if (!state) return;
    state.ops.push({ ...op, id: op.id || Math.random().toString(36).slice(2), ts: Date.now(), attempts: 0, tenant: op.tenant || currentTenant() } as QueuedOp);
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
