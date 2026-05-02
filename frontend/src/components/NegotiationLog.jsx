import React, { useMemo, useState } from "react";
import { useSessionStore } from "../store/sessionStore";

export const NegotiationLog = ({ sessionId }) => {
  const [collapsed, setCollapsed] = useState(true);
  const messages = useSessionStore((state) => state.messages);

  const negotiationMessages = useMemo(
    () =>
      (messages || []).filter(
        (m) =>
          m?.type === "negotiation_update" ||
          m?.type === "a2a_message" ||
          m?.metadata?.message_type === "CHALLENGE",
      ),
    [messages],
  );

  return (
    <div
      style={{
        margin: "12px 16px",
        border: "1px solid rgba(148,163,184,0.2)",
        borderRadius: "10px",
        background: "rgba(2,8,23,0.7)",
      }}
    >
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        style={{
          width: "100%",
          textAlign: "left",
          background: "transparent",
          border: "none",
          color: "#94a3b8",
          padding: "8px 10px",
          cursor: "pointer",
          fontSize: "12px",
        }}
      >
        NegotiationLog ({negotiationMessages.length}) - {collapsed ? "collapsed" : "open"} - session {sessionId || "-"}
      </button>
      {collapsed ? null : (
        <div style={{ maxHeight: "160px", overflowY: "auto", padding: "0 10px 10px", fontSize: "11px", color: "#cbd5e1" }}>
          {negotiationMessages.length === 0 ? (
            <div style={{ color: "#64748b" }}>No negotiation events yet.</div>
          ) : (
            negotiationMessages.map((m) => (
              <div key={m.id} style={{ padding: "4px 0", borderBottom: "1px dashed rgba(148,163,184,0.15)" }}>
                {m.type} - {m.content || m.message || ""}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default NegotiationLog;
