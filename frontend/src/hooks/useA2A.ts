import { useCallback, useEffect, useRef, useState } from "react";

export interface A2AMessage {
  sender: string;
  receiver: string;
  type: string;
  content: string;
  metadata: any;
  issue_id?: string;
  round: number;
  confidence?: number;
  message_id: string;
  timestamp: string;
  evidence?: any[];
}

export interface ImpactRadius {
  direct: number[];
  downstream: number[];
  upstream: number[];
  cross_file: any[];
  impact_chain: [number, number, string][];
}

const newMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export const useA2A = (sessionId: string) => {
  const wsRef = useRef<WebSocket | null>(null);
  const [a2aMessages, setA2aMessages] = useState<A2AMessage[]>([]);
  const [impactRadius, setImpactRadius] = useState<ImpactRadius | null>(null);
  const [arbitrationPending, setArbitrationPending] = useState(false);
  const [arbitrationData, setArbitrationData] = useState<any>(null);
  const [challengeTimeout, setChallengeTimeout] = useState(60);
  const [surgicalScope, setSurgicalScope] = useState<number[] | null>(null);

  useEffect(() => {
    setA2aMessages([]);
    setImpactRadius(null);
    setArbitrationPending(false);
    setArbitrationData(null);
    setSurgicalScope(null);

    if (!sessionId) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/${sessionId}`);
    wsRef.current = socket;

    socket.onmessage = (event) => {
      let payload: any = null;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!payload || typeof payload !== "object") return;

      if (payload.type === "a2a_message") {
        const meta = payload.metadata || {};
        const msg: A2AMessage = {
          sender: meta.sender || "SYSTEM",
          receiver: meta.receiver || "SYSTEM",
          type: meta.type || "A2A",
          content: meta.content || payload.content || "",
          metadata: meta.metadata || {},
          issue_id: meta.issue_id || undefined,
          round: Number(meta.round || payload.round || 0),
          confidence: meta.confidence ?? undefined,
          message_id: meta.message_id || newMessageId(),
          timestamp: meta.timestamp || new Date().toISOString(),
          evidence: meta.evidence || [],
        };
        setA2aMessages((prev) => [...prev, msg]);
        return;
      }

      if (payload.type === "impact_map_update") {
        setImpactRadius(payload.metadata?.impact_radius || payload.impact_radius || null);
        return;
      }

      if (payload.type === "arbitration_required") {
        setArbitrationPending(true);
        setArbitrationData(payload.metadata || payload);
        return;
      }

      if (payload.type === "surgical_review_start") {
        const scope = payload.metadata?.scope_lines || payload.scope_lines || null;
        setSurgicalScope(Array.isArray(scope) ? scope : null);
      }
    };

    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  const resolveArbitration = useCallback(
    async (decision: "accept_chanakya" | "accept_aryabhata", issueId: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({
          type: "arbitration_decision",
          session_id: sessionId,
          issue_id: issueId,
          decision,
        }),
      );
      setArbitrationPending(false);
      setArbitrationData(null);
    },
    [sessionId],
  );

  const updateChallengeTimeout = useCallback(
    async (seconds: number) => {
      setChallengeTimeout(seconds);
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({
          type: "update_config",
          session_id: sessionId,
          challenge_timeout: seconds,
        }),
      );
    },
    [sessionId],
  );

  const getNegotiationThread = useCallback(
    (issueId: string) => a2aMessages.filter((message) => message.issue_id === issueId),
    [a2aMessages],
  );

  return {
    a2aMessages,
    impactRadius,
    arbitrationPending,
    arbitrationData,
    challengeTimeout,
    surgicalScope,
    resolveArbitration,
    updateChallengeTimeout,
    getNegotiationThread,
  };
};
