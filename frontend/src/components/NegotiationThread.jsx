import React from "react";

export const ConfidenceMeter = ({ confidenceScore = 0 }) => (
  <div style={{ marginTop: 6 }}>
    <div style={{ fontSize: 10, color: "#94a3b8", marginBottom: 3 }}>confidence score</div>
    <div style={{ width: "100%", height: 6, borderRadius: 999, background: "rgba(148,163,184,0.2)" }}>
      <div
        style={{
          width: `${Math.max(0, Math.min(100, confidenceScore))}%`,
          height: "100%",
          borderRadius: 999,
          background: "#60a5fa",
        }}
      />
    </div>
  </div>
);

export const NegotiationThread = ({ issueId, challenge, response }) => {
  if (!challenge) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ color: "#f59e0b", fontSize: 11 }}>NegotiationThread for issue #{issueId}</div>
      <div
        style={{
          marginTop: 6,
          marginLeft: 18,
          paddingLeft: 12,
          borderLeft: "2px solid rgba(245,158,11,0.35)",
          background: "rgba(245,158,11,0.08)",
          borderRadius: 8,
          padding: 8,
        }}
      >
        <div style={{ fontSize: 11, color: "#fbbf24" }}>challenge reply bubble (indented challenge style)</div>
        <div style={{ marginTop: 4, fontSize: 12, color: "#e2e8f0" }}>{challenge}</div>
        <ConfidenceMeter confidenceScore={82} />
      </div>
      {response ? (
        <div style={{ marginTop: 6, marginLeft: 38, fontSize: 12, color: "#cbd5e1" }}>{response}</div>
      ) : null}
    </div>
  );
};

export default NegotiationThread;
