import React, { useState } from "react";

import type { ImpactRadius } from "../hooks/useA2A";

type ThreadMessage = {
  sender: string;
  receiver: string;
  type: string;
  content: string;
  confidence?: number;
  timestamp?: string;
  evidence?: Array<{ source: string; url?: string }>;
};

export const NegotiationThread: React.FC<{
  thread: ThreadMessage[];
  issueId: string;
}> = ({ thread, issueId }) => {
  const [expanded, setExpanded] = useState(false);
  if (!thread || !thread.length) return null;

  const getMessageIcon = (type: string) => {
    switch (type) {
      case "CHALLENGE":
        return "⚔️";
      case "CHALLENGE_WITHDRAW":
        return "✅";
      case "CHALLENGE_UPHOLD":
        return "🛡️";
      case "ESCALATE_TO_USER":
        return "👤";
      case "TIMEOUT":
        return "⏱️";
      default:
        return "💬";
    }
  };

  const getMessageColor = (type: string) => {
    switch (type) {
      case "CHALLENGE":
        return "#f59e0b";
      case "CHALLENGE_WITHDRAW":
        return "#10b981";
      case "CHALLENGE_UPHOLD":
        return "#ef4444";
      case "ESCALATE_TO_USER":
        return "#8b5cf6";
      default:
        return "#6b7280";
    }
  };

  return (
    <div
      style={{
        marginLeft: "20px",
        marginTop: "8px",
        borderLeft: "2px solid rgba(255,255,255,0.1)",
        paddingLeft: "12px",
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          background: "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: "6px",
          color: "#a0aec0",
          padding: "4px 10px",
          fontSize: "11px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        {expanded ? "▼" : "▶"}
        {thread.length} negotiation message{thread.length !== 1 ? "s" : ""}
        <span
          style={{
            background: "#3b82f6",
            color: "white",
            padding: "1px 6px",
            borderRadius: "4px",
            fontSize: "10px",
          }}
        >
          #{issueId}
        </span>
      </button>

      {expanded && (
        <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          {thread.map((msg, idx) => (
            <div
              key={`${issueId}-${idx}`}
              style={{
                background: "rgba(0,0,0,0.2)",
                border: `1px solid ${getMessageColor(msg.type)}30`,
                borderRadius: "8px",
                padding: "8px 12px",
                fontSize: "12px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                <span style={{ color: getMessageColor(msg.type), fontWeight: 600 }}>
                  {getMessageIcon(msg.type)} {msg.sender} → {msg.receiver}
                </span>
                <span style={{ color: "#4a5568", fontSize: "10px" }}>{msg.timestamp || ""}</span>
              </div>
              <div style={{ color: "#e2e8f0", lineHeight: "1.4" }}>{msg.content}</div>
              {typeof msg.confidence === "number" ? (
                <div style={{ marginTop: "4px", color: "#f59e0b", fontSize: "11px" }}>
                  Confidence: {Math.round(msg.confidence * 100)}%
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const ImpactMap: React.FC<{
  impactRadius: ImpactRadius;
  touchedLines: number[];
}> = ({ impactRadius, touchedLines }) => {
  const [expanded, setExpanded] = useState(false);
  const hasImpact =
    (impactRadius?.downstream || []).length > 0 ||
    (impactRadius?.cross_file || []).length > 0;
  if (!hasImpact) return null;

  return (
    <div
      style={{
        margin: "8px 0",
        background: "rgba(245,158,11,0.1)",
        border: "1px solid rgba(245,158,11,0.3)",
        borderRadius: "8px",
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          color: "#f59e0b",
          padding: "8px 12px",
          textAlign: "left",
          cursor: "pointer",
          fontSize: "12px",
          fontWeight: 600,
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        {expanded ? "▼" : "▶"}
        Cross-line Impact Detected
        <span
          style={{
            background: "rgba(245,158,11,0.3)",
            padding: "1px 6px",
            borderRadius: "4px",
            fontSize: "10px",
          }}
        >
          {(impactRadius.downstream || []).length} downstream
          {(impactRadius.cross_file || []).length > 0
            ? ` · ${(impactRadius.cross_file || []).length} cross-file`
            : ""}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: "0 12px 12px", fontSize: "12px" }}>
          {(impactRadius.impact_chain || []).map((chain, i) => (
            <div
              key={`chain-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "4px 0",
                color: "#e2e8f0",
              }}
            >
              <span
                style={{
                  background: "rgba(239,68,68,0.2)",
                  color: "#f87171",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  fontFamily: "monospace",
                }}
              >
                Line {chain[0]}
              </span>
              <span style={{ color: "#f59e0b" }}>→</span>
              <span
                style={{
                  background: "rgba(245,158,11,0.2)",
                  color: "#fcd34d",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  fontFamily: "monospace",
                }}
              >
                Line {chain[1]}
              </span>
              <span style={{ color: "#9ca3af", flex: 1 }}>{chain[2]}</span>
            </div>
          ))}

          {(impactRadius.cross_file || []).map((impact: any, i: number) => (
            <div
              key={`cross-${i}`}
              style={{
                marginTop: "4px",
                padding: "6px",
                background: "rgba(0,0,0,0.2)",
                borderRadius: "6px",
                color: "#e2e8f0",
              }}
            >
              <span style={{ color: "#f59e0b" }}>Cross-file: </span>
              {impact.description}
            </div>
          ))}
          {touchedLines?.length ? (
            <div style={{ marginTop: "6px", color: "#94a3b8", fontSize: "11px" }}>
              Touched lines: {touchedLines.join(", ")}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export const TimeoutSlider: React.FC<{
  value: number;
  onChange: (val: number) => void;
}> = ({ value, onChange }) => (
  <div style={{ padding: "12px" }}>
    <label
      style={{
        color: "#a0aec0",
        fontSize: "12px",
        display: "flex",
        justifyContent: "space-between",
      }}
    >
      <span>Challenge Timeout</span>
      <span style={{ color: "#60a5fa" }}>{value}s</span>
    </label>
    <input
      type="range"
      min="10"
      max="300"
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value, 10))}
      style={{ width: "100%", marginTop: "6px", accentColor: "#60a5fa" }}
    />
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        color: "#4a5568",
        fontSize: "10px",
      }}
    >
      <span>10s</span>
      <span>60s (default)</span>
      <span>5m</span>
    </div>
  </div>
);
