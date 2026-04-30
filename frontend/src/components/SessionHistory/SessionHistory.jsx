import { useMemo, useState } from "react";
import useSessionStore from "../../store/sessionStore";

function shortId(id = "") {
  return id.slice(0, 8);
}

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "running") return "#4fffb0";
  if (normalized === "completed") return "#4f9eff";
  if (normalized === "interrupted") return "#ffb347";
  if (normalized === "failed") return "#ff7f7f";
  if (normalized === "submitted") return "#9b6dff";
  return "var(--text-secondary)";
}

function relativeTime(iso) {
  if (!iso) return "unknown";
  const deltaMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(deltaMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours > 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

export default function SessionHistory() {
  const {
    sessions,
    loadingSessions,
    fetchSessions,
    loadSession,
    resumeSession,
    deleteSession,
    resetConversation,
  } = useSessionStore();

  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return sessions;
    return sessions.filter((session) => {
      const status = String(session.status || "").toLowerCase();
      const subsystem = String(session.subsystem || "").toLowerCase();
      const id = String(session.session_id || "").toLowerCase();
      return status.includes(q) || subsystem.includes(q) || id.includes(q);
    });
  }, [sessions, query]);

  if (collapsed) {
    return (
      <button type="button" className="btn secondary" onClick={() => setCollapsed(false)}>
        🕘 History
      </button>
    );
  }

  return (
    <div className="glass card" style={{ maxHeight: "70vh", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h4>Session History</h4>
        <button type="button" className="btn secondary" onClick={() => setCollapsed(true)}>Hide</button>
      </div>

      <div style={{ display: "grid", gap: 8, marginBottom: 8 }}>
        <button
          type="button"
          className="btn"
          onClick={() => {
            resetConversation();
          }}
        >
          New Session
        </button>
        <button type="button" className="btn secondary" onClick={() => fetchSessions()} disabled={loadingSessions}>
          {loadingSessions ? "Loading..." : "Refresh"}
        </button>
        <input
          className="input"
          value={query}
          placeholder="Filter by status/subsystem"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        {filtered.map((session) => (
          <div key={session.session_id} className="glass" style={{ padding: 10, borderRadius: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <strong>{shortId(session.session_id)}</strong>
              <span className="badge" style={{ color: statusTone(session.status) }}>{String(session.status || "unknown").toUpperCase()}</span>
            </div>

            <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
              <span className="badge">{session.subsystem || "audio"}</span>
              <span className="badge">Round {session.current_round || 0}/{session.max_rounds || 5}</span>
              <span className="badge">{session.verdict || "PENDING"}</span>
            </div>

            <p className="small" style={{ marginTop: 6 }}>{relativeTime(session.updated_at || session.created_at)}</p>

            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <button type="button" className="btn secondary" onClick={() => loadSession(session.session_id)}>👁️ View</button>
              {String(session.status || "").toLowerCase() === "interrupted" ? (
                <button type="button" className="btn secondary" onClick={() => resumeSession(session.session_id)}>▶️ Resume</button>
              ) : null}
              <button type="button" className="btn secondary" onClick={() => deleteSession(session.session_id)}>🗑️ Delete</button>
            </div>
          </div>
        ))}
        {!filtered.length ? <p className="small">No sessions found.</p> : null}
      </div>
    </div>
  );
}
