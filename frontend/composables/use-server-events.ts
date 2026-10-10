import { useViewPreferences } from "./use-preferences";
import { ref, watch } from "vue";

// Groza 定制版（覆盖上游同名文件）：
// 在上游断线重连基础上补齐页面生命周期处理——
// 1. pagehide 时主动关闭连接，避免页面进入 bfcache 时浏览器强杀 WS
//    并在控制台刷 "Page entered Back-Forward Cache" 报错；
// 2. pageshow(persisted) / 重新可见 / 网络恢复时立即重连（不等退避）；
// 3. onerror 降为 debug，真正的作用交给 onclose 的重连。

export enum ServerEvent {
  EntityMutation = "entity.mutation",
  TagMutation = "tag.mutation",
  UserMutation = "user.mutation",
  ExportMutation = "export.mutation",
  ImportMutation = "import.mutation",
}

export type EventMessage = {
  event: ServerEvent;
};

let socket: WebSocket | null = null;
let currentTenantId: string | null = null;
let watcherSetup = false;
let lifecycleSetup = false;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let messageHandler: ((m: EventMessage) => void) | null = null;

// 连接状态（模块级共享）：页面指示灯（如台账顶栏 wsOk）直接读这个 ref
export const serverEventsConnected = ref(false);

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;

const listeners = new Map<ServerEvent, (() => void)[]>();

function getWebSocketProtocols() {
  const auth = useAuthContext();
  if (!auth.attachmentToken) {
    return undefined;
  }

  // Browser WebSocket APIs cannot set arbitrary headers, so pass auth in the
  // subprotocol header and parse it server-side.
  return ["hb-auth", auth.attachmentToken];
}

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function nextReconnectDelay() {
  const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempts, RECONNECT_MAX_DELAY_MS);
  reconnectAttempts += 1;
  return delay;
}

function scheduleReconnect() {
  if (reconnectTimer !== null) {
    return;
  }

  const delay = nextReconnectDelay();
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (!useAuthContext().attachmentToken) {
      return;
    }
    connect();
  }, delay);
}

function connect() {
  if (!messageHandler) {
    return;
  }
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  let protocol = "ws";
  if (window.location.protocol === "https:") {
    protocol = "wss";
  }

  const dev = import.meta.dev;

  const host = dev ? window.location.host.replace("3000", "7745") : window.location.host;

  let url = `${protocol}://${host}/api/v1/ws/events`;
  if (currentTenantId) {
    url += `?tenant=${currentTenantId}`;
  }

  const protocols = getWebSocketProtocols();
  if (!protocols) {
    return;
  }

  const ws = new WebSocket(url, protocols);
  const onmessage = messageHandler;

  ws.onopen = () => {
    reconnectAttempts = 0;
    clearReconnectTimer();
    serverEventsConnected.value = true;
    console.debug("connected to server");
  };

  ws.onclose = () => {
    console.debug("disconnected from server");
    if (socket === ws) {
      socket = null;
    }
    serverEventsConnected.value = false;
    scheduleReconnect();
  };

  ws.onerror = () => {
    // 错误事件之后必然紧跟 close 事件，由 onclose 统一安排重连；
    // 这里不再 console.error，避免弱网/休眠唤醒时刷无意义的红字。
    console.debug("websocket error (reconnect handled via onclose)");
  };

  const thorttled = new Map<ServerEvent, (m: EventMessage) => void>();

  thorttled.set(ServerEvent.EntityMutation, useThrottleFn(onmessage, 1000));
  thorttled.set(ServerEvent.TagMutation, useThrottleFn(onmessage, 1000));
  thorttled.set(ServerEvent.UserMutation, useThrottleFn(onmessage, 1000));
  thorttled.set(ServerEvent.ExportMutation, useThrottleFn(onmessage, 500));
  thorttled.set(ServerEvent.ImportMutation, useThrottleFn(onmessage, 500));

  ws.onmessage = msg => {
    const pm = JSON.parse(msg.data);
    const fn = thorttled.get(pm.event);
    if (fn) {
      fn(pm);
    }
  };

  socket = ws;
}

function closeForFreeze() {
  // 页面即将被冻结（bfcache）或卸载：主动关闭，浏览器就无需代劳，
  // 也不会在控制台打 "Page entered Back-Forward Cache"。
  clearReconnectTimer();
  serverEventsConnected.value = false;
  if (socket) {
    socket.onopen = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;
    try {
      socket.close();
    } catch (_e) {
      /* 忽略 */
    }
    socket = null;
  }
}

function resumeFromFreeze() {
  // 从 bfcache 恢复 / 后台回到前台 / 网络恢复：连接已死则立即重连。
  if (!messageHandler) {
    return;
  }
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  socket = null;
  reconnectAttempts = 0;
  clearReconnectTimer();
  connect();
}

function setupLifecycle() {
  if (lifecycleSetup || !import.meta.client) {
    return;
  }
  lifecycleSetup = true;
  window.addEventListener("pagehide", closeForFreeze);
  window.addEventListener("pageshow", e => {
    if (e.persisted) {
      resumeFromFreeze();
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      resumeFromFreeze();
    }
  });
  window.addEventListener("online", resumeFromFreeze);
}

export function onServerEvent(event: ServerEvent, callback: () => void) {
  const prefs = useViewPreferences();
  currentTenantId = prefs.value.collectionId || null;

  messageHandler = e => {
    console.debug("received event", e);
    listeners.get(e.event)?.forEach(c => c());
  };
  setupLifecycle();

  if (!watcherSetup) {
    watch(
      () => prefs.value.collectionId,
      newId => {
        currentTenantId = newId || null;
        reconnectAttempts = 0;
        clearReconnectTimer();

        if (socket) {
          socket.onclose = null;
          socket.close();
          socket = null;
        }

        connect();
      }
    );
    watcherSetup = true;
  }

  if (socket === null) {
    reconnectAttempts = 0;
    clearReconnectTimer();
    connect();
  }

  onMounted(() => {
    if (!listeners.has(event)) {
      listeners.set(event, []);
    }
    listeners.get(event)?.push(callback);
  });

  onUnmounted(() => {
    const got = listeners.get(event);
    if (got) {
      listeners.set(
        event,
        got.filter(c => c !== callback)
      );
    }

    if (listeners.get(event)?.length === 0) {
      listeners.delete(event);
    }
  });
}
