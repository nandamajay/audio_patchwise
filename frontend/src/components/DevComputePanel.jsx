import React, { useEffect, useRef, useState } from "react";
import { useSessionStore } from "../store/sessionStore";

export const DevComputePanel = ({ sessionId, agent }) => {
  const terminalRef = useRef(null);
  const [lines, setLines] = useState([]);
  const [progress, setProgress] = useState(0);
  const [isExpanded, setIsExpanded] = useState(true);
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
      if (data.type === "dev_compute_output" && data.session_id === sessionId && data.agent === agent) {
        setLines((prev) => {
          const next = [
            ...prev,
            {
              text: data.line,
              type: data.line_type || "info",
              ts: Date.now(),
            },
          ];
          return next.slice(-100);
        });
        if (data.progress !== undefined) setProgress(Number(data.progress || 0));
        if (terminalRef.current) {
          terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
        }
      }
    };

    socket.addEventListener("message", handler);
    return () => socket.removeEventListener("message", handler);
  }, [socket, sessionId, agent]);

  const LINE_COLORS = {
    info: "#94a3b8",
    success: "#10b981",
    error: "#ef4444",
    command: "#60a5fa",
    progress: "#f59e0b",
    warning: "#f97316",
  };

  const agentColor = agent === "chanakya" ? "#60a5fa" : "#a78bfa";
  const agentName = agent === "chanakya" ? "CHANAKYA" : "ARYABHATA";

  return (
    <div
      style={{
        background: "rgba(2,8,23,0.95)",
        border: `1px solid ${agentColor}22`,
        borderRadius: "12px",
        overflow: "hidden",
        marginBottom: "8px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 12px",
          background: `${agentColor}11`,
          borderBottom: `1px solid ${agentColor}22`,
          cursor: "pointer",
        }}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ color: agentColor, fontSize: "12px" }}>[]</span>
          <span style={{ color: agentColor, fontFamily: "monospace", fontSize: "12px", fontWeight: 700 }}>
            {agentName} - Dev-Compute Live
          </span>
          <span
            style={{
              background: `${agentColor}22`,
              color: agentColor,
              borderRadius: "20px",
              padding: "1px 8px",
              fontSize: "10px",
            }}
          >
            hu-nandam-hyd
          </span>
        </div>
        <span style={{ color: "#64748b", fontSize: "12px" }}>{isExpanded ? "v" : ">"}</span>
      </div>

      {isExpanded ? (
        <>
          {progress > 0 && progress < 100 ? (
            <div style={{ background: "#1e293b", height: "3px" }}>
              <div
                style={{
                  height: "100%",
                  width: `${progress}%`,
                  background: `linear-gradient(90deg, ${agentColor}, ${agentColor}88)`,
                  transition: "width 0.3s",
                }}
              />
            </div>
          ) : null}

          <div
            ref={terminalRef}
            style={{
              height: "160px",
              overflowY: "auto",
              padding: "8px 12px",
              fontFamily: "monospace",
              fontSize: "11px",
              lineHeight: "1.6",
            }}
          >
            {lines.length === 0 ? (
              <div style={{ color: "#374151", fontStyle: "italic" }}>Waiting for dev-compute output...</div>
            ) : (
              lines.map((line, i) => (
                <div key={i} style={{ color: LINE_COLORS[line.type] || "#94a3b8", wordBreak: "break-all" }}>
                  {line.type === "command" ? "$ " : ""}
                  {line.text}
                </div>
              ))
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};

export default DevComputePanel;
