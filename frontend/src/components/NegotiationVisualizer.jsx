import React, { useEffect, useState } from "react";
import { useSessionStore } from "../store/sessionStore";

export const NegotiationVisualizer = ({ sessionId }) => {
  const [negotiations, setNegotiations] = useState([]);
  const [activeTimeout, setActiveTimeout] = useState(null);
  const socket = useSessionStore((state) => state.socket);

  useEffect(() => {
    if (!socket || !sessionId) return undefined;

    const handler = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.type !== "negotiation_update" || data.session_id !== sessionId) return;

      setNegotiations((prev) => {
        const idx = prev.findIndex((n) => n.issue_id === data.issue_id);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = { ...updated[idx], ...data };
          return updated;
        }
        return [...prev, data];
      });

      if (data.timeout_remaining !== undefined) {
        setActiveTimeout({
          issue_id: data.issue_id,
          remaining: Number(data.timeout_remaining || 0),
          total: 60,
        });
      }
    };

    socket.addEventListener("message", handler);
    return () => socket.removeEventListener("message", handler);
  }, [socket, sessionId]);

  useEffect(() => {
    if (!activeTimeout || activeTimeout.remaining <= 0) return undefined;
    const timer = setInterval(() => {
      setActiveTimeout((prev) => {
        if (!prev || prev.remaining <= 1) return null;
        return { ...prev, remaining: prev.remaining - 1 };
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [activeTimeout?.issue_id]);

  const activeNegotiations = negotiations.filter(
    (n) => !["withdrawn", "upheld_resolved", "auto_proceeded"].includes(n.state),
  );
  if (activeNegotiations.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        right: "16px",
        top: "120px",
        width: "280px",
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      {activeNegotiations.map((neg) => (
        <NegotiationCard
          key={neg.issue_id}
          negotiation={neg}
          timeout={activeTimeout?.issue_id === neg.issue_id ? activeTimeout : null}
        />
      ))}
    </div>
  );
};

const NegotiationCard = ({ negotiation, timeout }) => {
  const STATE_CONFIG = {
    challenging: { color: "#ef4444", icon: "X", label: "ARYABHATA Challenging" },
    evaluating: { color: "#f59e0b", icon: "?", label: "CHANAKYA Re-evaluating" },
    clarifying: { color: "#06b6d4", icon: "i", label: "Agents Clarifying" },
    arbitration: { color: "#f97316", icon: "!", label: "User Arbitration Needed" },
    withdrawn: { color: "#10b981", icon: "+", label: "CHANAKYA Withdrew" },
    upheld: { color: "#6366f1", icon: "=", label: "CHANAKYA Upheld" },
  };
  const config = STATE_CONFIG[negotiation.state] || STATE_CONFIG.challenging;

  return (
    <div
      style={{
        background: "rgba(15,23,42,0.95)",
        border: `1px solid ${config.color}44`,
        borderRadius: "10px",
        padding: "10px 12px",
        backdropFilter: "blur(12px)",
        boxShadow: `0 0 20px ${config.color}11`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
        <span style={{ fontSize: "11px", fontWeight: 700, color: config.color }}>
          {config.icon} {config.label}
        </span>
        {timeout ? (
          <span
            style={{
              background: `${config.color}22`,
              color: config.color,
              borderRadius: "20px",
              padding: "1px 8px",
              fontSize: "10px",
              fontFamily: "monospace",
            }}
          >
            t {timeout.remaining}s
          </span>
        ) : null}
      </div>

      <div style={{ color: "#94a3b8", fontSize: "11px", marginBottom: "6px" }}>
        Issue #{negotiation.issue_id} - {negotiation.issue_type}
      </div>

      {["challenging", "evaluating"].includes(negotiation.state) ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <ConfidenceMeter label="CHANAKYA" value={Number(negotiation.chanakya_confidence || 0)} color="#60a5fa" />
          <ConfidenceMeter label="ARYABHATA" value={Number(negotiation.aryabhata_confidence || 0)} color="#a78bfa" />
        </div>
      ) : null}

      {timeout ? (
        <div style={{ marginTop: "8px", background: "#1e293b", borderRadius: "4px", height: "3px" }}>
          <div
            style={{
              height: "100%",
              width: `${(timeout.remaining / timeout.total) * 100}%`,
              background: config.color,
              borderRadius: "4px",
              transition: "width 1s linear",
            }}
          />
        </div>
      ) : null}

      {negotiation.state === "arbitration" ? (
        <button
          style={{
            marginTop: "8px",
            width: "100%",
            padding: "6px",
            background: `${config.color}22`,
            border: `1px solid ${config.color}44`,
            borderRadius: "6px",
            color: config.color,
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Arbitrate Now
        </button>
      ) : null}
    </div>
  );
};

const ConfidenceMeter = ({ label, value, color }) => (
  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
    <span style={{ color: "#64748b", fontSize: "10px", minWidth: "60px", fontFamily: "monospace" }}>{label}</span>
    <div style={{ flex: 1, background: "#1e293b", borderRadius: "4px", height: "6px" }}>
      <div style={{ height: "100%", width: `${value}%`, background: color, borderRadius: "4px", transition: "width 0.5s" }} />
    </div>
    <span style={{ color, fontSize: "10px", fontFamily: "monospace", minWidth: "30px" }}>{value}%</span>
  </div>
);

export default NegotiationVisualizer;
