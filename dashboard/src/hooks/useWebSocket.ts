"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { getWSUrl, type WSMessage } from "@/lib/ws";

export function useWebSocket(
  taskId?: number,
  onMessage?: (msg: WSMessage) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  const [connected, setConnected] = useState(false);

  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = getWSUrl(taskId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSMessage;
      onMessageRef.current?.(msg);
    };

    ws.onclose = () => {
      setConnected(false);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [taskId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { ws: wsRef, connected };
}
