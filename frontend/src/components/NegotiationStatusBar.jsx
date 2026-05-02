import React from "react";
import { useSessionStore } from "../store/sessionStore";

export const NegotiationStatusBar = ({ sessionId }) => {
  const negotiationState = useSessionStore((state) => state.agentStatus?.negotiation_state || "idle");
  if (!sessionId) return null;
  return (
    <div
      style={{
        margin: "8px 16px",
        padding: "6px 10px",
        borderRadius: "8px",
        border: "1px solid rgba(245,158,11,0.35)",
        background: "rgba(245,158,11,0.12)",
        color: "#fbbf24",
        fontSize: "11px",
        fontFamily: "monospace",
      }}
    >
      NegotiationStatus (a2a status bar): negotiation active = {String(negotiationState !== "idle")}
    </div>
  );
};

export default NegotiationStatusBar;
