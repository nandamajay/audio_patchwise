import React from "react";
import { useSessionStore } from "../store/sessionStore";

const CHANAKYA_AVATAR = () => (
  <svg width="32" height="32" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="14" fill="none" stroke="#60a5fa" strokeWidth="2" />
    <circle cx="11" cy="13" r="2.5" fill="#60a5fa" />
    <circle cx="21" cy="13" r="2.5" fill="#60a5fa" />
    <path d="M8 13 Q6 13 6 11" stroke="#60a5fa" strokeWidth="1.5" fill="none" />
    <path d="M24 13 Q26 13 26 11" stroke="#60a5fa" strokeWidth="1.5" fill="none" />
    <path d="M12 21 Q16 24 20 21" stroke="#60a5fa" strokeWidth="1.5" fill="none" />
    <line x1="18" y1="6" x2="18" y2="3" stroke="#60a5fa" strokeWidth="1.5" />
    <circle cx="18" cy="2" r="1.5" fill="#60a5fa" />
  </svg>
);

const ARYABHATA_AVATAR = () => (
  <svg width="32" height="32" viewBox="0 0 32 32">
    <rect x="4" y="4" width="24" height="24" rx="4" fill="none" stroke="#a78bfa" strokeWidth="2" />
    <rect x="8" y="11" width="5" height="3" rx="1" fill="#a78bfa" />
    <rect x="19" y="11" width="5" height="3" rx="1" fill="#a78bfa" />
    <path d="M13 21 Q16 24 19 21" stroke="#a78bfa" strokeWidth="1.5" fill="none" />
    <path d="M10 4 L8 1 M16 4 L16 1 M22 4 L24 1" stroke="#a78bfa" strokeWidth="1.5" />
    <text x="9" y="20" fontSize="5" fill="#a78bfa" fontFamily="monospace">
      {"</>"}
    </text>
  </svg>
);

const STATUS_COLORS = {
  idle: "#6b7280",
  thinking: "#f59e0b",
  fixing: "#3b82f6",
  validating: "#8b5cf6",
  challenging: "#ef4444",
  waiting: "#6b7280",
  preloading: "#06b6d4",
  lgtm: "#10b981",
  ssh_connected: "#10b981",
  ssh_disconnected: "#ef4444",
  ssh_reconnecting: "#f59e0b",
  docker_fallback: "#f97316",
};

const STATUS_LABELS = {
  idle: "Idle",
  thinking: "Analyzing...",
  fixing: "Applying Fix",
  validating: "Validating",
  challenging: "Challenging",
  waiting: "Waiting",
  preloading: "Pre-loading",
  lgtm: "LGTM",
  ssh_connected: "Connected",
  ssh_disconnected: "Disconnected",
  ssh_reconnecting: "Reconnecting...",
  docker_fallback: "Local Fallback",
};

export const AgentStatusBar = ({ sessionId }) => {
  const { agentStatus, devComputeStatus } = useSessionStore();
  const chanakya = agentStatus?.chanakya || {
    status: "idle",
    screen: null,
    files_changed: 0,
    current_command: null,
  };
  const aryabhata = agentStatus?.aryabhata || {
    status: "idle",
    screen: null,
    symbols_indexed: 0,
    current_command: null,
  };
  const devCompute = devComputeStatus || { status: "ssh_disconnected", host: "hu-nandam-hyd" };

  if (!sessionId) return null;

  return (
    <div
      style={{
        display: "flex",
        gap: "12px",
        padding: "12px 16px",
        background: "rgba(15,23,42,0.85)",
        borderBottom: "1px solid rgba(99,102,241,0.2)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 100,
        alignItems: "center",
      }}
    >
      <AgentPanel
        avatar={<CHANAKYA_AVATAR />}
        name="CHANAKYA"
        subtitle="Analyst & Patch Engineer"
        status={chanakya.status}
        detail={
          chanakya.current_command
            ? `$ ${String(chanakya.current_command).slice(0, 40)}...`
            : `Files: ${chanakya.files_changed} changed`
        }
        screen={chanakya.screen}
        color="#60a5fa"
      />

      <A2ABridgeIndicator status={agentStatus?.negotiation_state} />

      <AgentPanel
        avatar={<ARYABHATA_AVATAR />}
        name="ARYABHATA"
        subtitle="Validator & Quality Gatekeeper"
        status={aryabhata.status}
        detail={
          aryabhata.current_command
            ? `$ ${String(aryabhata.current_command).slice(0, 40)}...`
            : `Symbols: ${aryabhata.symbols_indexed}`
        }
        screen={aryabhata.screen}
        color="#a78bfa"
        right
      />

      <DevComputePill status={devCompute.status} host={devCompute.host} />
    </div>
  );
};

const AgentPanel = ({ avatar, name, subtitle, status, detail, screen, color, right }) => (
  <div
    style={{
      flex: 1,
      display: "flex",
      alignItems: "center",
      gap: "10px",
      padding: "8px 12px",
      background: `rgba(${color === "#60a5fa" ? "96,165,250" : "167,139,250"},0.08)`,
      borderRadius: "10px",
      border: `1px solid ${color}22`,
      flexDirection: right ? "row-reverse" : "row",
    }}
  >
    <div style={{ position: "relative" }}>
      {avatar}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          right: 0,
          width: "10px",
          height: "10px",
          borderRadius: "50%",
          background: STATUS_COLORS[status] || "#6b7280",
          border: "2px solid #0f172a",
          transition: "background 0.3s",
        }}
      />
    </div>
    <div style={{ textAlign: right ? "right" : "left" }}>
      <div style={{ color, fontWeight: 700, fontSize: "13px", fontFamily: "monospace" }}>{name}</div>
      <div style={{ color: "#94a3b8", fontSize: "10px" }}>{subtitle}</div>
      <div style={{ display: "flex", gap: "6px", marginTop: "4px", flexDirection: right ? "row-reverse" : "row" }}>
        <StatusPill status={status} color={STATUS_COLORS[status]} />
        {screen ? <ScreenPill screen={screen} /> : null}
      </div>
      {detail ? (
        <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px", fontFamily: "monospace" }}>{detail}</div>
      ) : null}
    </div>
  </div>
);

const StatusPill = ({ status, color }) => (
  <span
    style={{
      background: `${color}22`,
      color,
      border: `1px solid ${color}44`,
      borderRadius: "20px",
      padding: "1px 8px",
      fontSize: "10px",
      fontWeight: 600,
      display: "flex",
      alignItems: "center",
      gap: "4px",
    }}
  >
    <span>{(status === "thinking" || status === "fixing" || status === "validating") ? "..." : "."}</span>
    {STATUS_LABELS[status] || status}
  </span>
);

const ScreenPill = ({ screen }) => (
  <span
    style={{
      background: "rgba(100,116,139,0.2)",
      color: "#94a3b8",
      borderRadius: "20px",
      padding: "1px 8px",
      fontSize: "10px",
      fontFamily: "monospace",
    }}
  >
    screen:{String(screen).slice(-8)}
  </span>
);

const A2ABridgeIndicator = ({ status }) => {
  const isActive = status && status !== "idle";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", minWidth: "80px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "4px", color: isActive ? "#f59e0b" : "#374151" }}>
        <span style={{ fontSize: "18px", transition: "all 0.3s" }}>{isActive ? "<->" : "-"}</span>
      </div>
      <span
        style={{
          fontSize: "9px",
          color: isActive ? "#f59e0b" : "#4b5563",
          fontWeight: 600,
          letterSpacing: "0.05em",
          textTransform: "uppercase",
        }}
      >
        {status === "challenging"
          ? "Challenge"
          : status === "clarifying"
            ? "Clarify"
            : status === "negotiating"
              ? "Negotiate"
              : "A2A Bridge"}
      </span>
    </div>
  );
};

const DevComputePill = ({ status, host }) => (
  <div
    style={{
      padding: "6px 12px",
      background: `${STATUS_COLORS[status] || "#6b7280"}11`,
      border: `1px solid ${STATUS_COLORS[status] || "#6b7280"}33`,
      borderRadius: "20px",
      display: "flex",
      alignItems: "center",
      gap: "6px",
      minWidth: "160px",
    }}
  >
    <span
      style={{
        width: "8px",
        height: "8px",
        borderRadius: "50%",
        background: STATUS_COLORS[status] || "#6b7280",
        flexShrink: 0,
      }}
    />
    <div>
      <div style={{ color: "#94a3b8", fontSize: "10px", fontFamily: "monospace" }}>{host}</div>
      <div style={{ color: STATUS_COLORS[status] || "#6b7280", fontSize: "10px", fontWeight: 600 }}>
        {STATUS_LABELS[status] || status}
      </div>
    </div>
  </div>
);

export default AgentStatusBar;
