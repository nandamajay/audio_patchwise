import { useCallback, useEffect, useRef } from "react";
import useSessionStore from "../store/sessionStore";

export default function useAgentStream(sessionId) {
  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const timerRef = useRef(null);
  const updateStreamingMessage = useSessionStore((state) => state.updateStreamingMessage);
  const markConnected = useSessionStore((state) => state.markConnected);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/${sessionId}`);
    wsRef.current = socket;

    socket.onopen = () => {
      retryRef.current = 0;
      markConnected(true);
      socket.send(JSON.stringify({ type: "start" }));
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        updateStreamingMessage(payload);
      } catch {
        // no-op
      }
    };

    socket.onclose = () => {
      markConnected(false);
      const delay = Math.min(30000, 500 * 2 ** retryRef.current);
      retryRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    socket.onerror = () => {
      socket.close();
    };
  }, [sessionId, markConnected, updateStreamingMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendEvent = useCallback((payload) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify(payload));
  }, []);

  return { sendEvent };
}
