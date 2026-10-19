/** WS 长连接：指数退避重连（Spec 12.4），不依赖消息重放。 */

import { isWsMessage, type WsMessage } from "./protocol";

const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000, 30000];

export interface WsHandle {
  close: () => void;
}

export function connectSessionStream(
  url: string,
  handlers: { onMessage: (message: WsMessage) => void; onStateChange?: (state: string) => void },
): WsHandle {
  let socket: WebSocket | null = null;
  let attempt = 0;
  let closedByUser = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}${url}`);

    socket.onopen = () => {
      attempt = 0;
      handlers.onStateChange?.("connected");
    };

    socket.onmessage = (event) => {
      try {
        const parsed: unknown = JSON.parse(event.data as string);
        if (isWsMessage(parsed)) handlers.onMessage(parsed);
      } catch {
        // 非法消息直接丢弃，不让脏数据打断整条流
      }
    };

    socket.onclose = () => {
      handlers.onStateChange?.("disconnected");
      if (closedByUser) return;
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
      attempt += 1;
      timer = setTimeout(open, delay);
    };

    socket.onerror = () => handlers.onStateChange?.("error");
  };

  open();

  return {
    close: () => {
      closedByUser = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    },
  };
}
