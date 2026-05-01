import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import useHistoryStore from "../stores/historyStore";

function badgeClass(verdict) {
  if (verdict === "LGTM") return "history-badge lgtm";
  if (verdict === "MAX_ROUNDS") return "history-badge max";
  if (verdict === "INTERRUPTED") return "history-badge interrupted";
  return "history-badge";
}

export default function HistorySidebar() {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const { sessions, fetchSessions } = useHistoryStore();

  useEffect(() => {
    fetchSessions().catch(() => undefined);
  }, [fetchSessions]);

  if (!expanded) {
    return (
      <button
        type="button"
        className="history-collapsed-pill"
        title="Open history"
        onClick={() => setExpanded(true)}
      >
        🕐
      </button>
    );
  }

  return (
    <aside className="glass history-sidebar">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>History</strong>
        <button type="button" className="btn secondary" onClick={() => setExpanded(false)}>Hide</button>
      </div>

      <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
        {sessions.slice(0, 10).map((session) => (
          <button
            key={session.id}
            type="button"
            className="history-sidebar-item"
            onClick={() => navigate("/history", { state: { sessionId: session.id } })}
          >
            <div className="history-sidebar-title" title={session.title}>{session.title?.slice(0, 40) || session.id}</div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span className={badgeClass(session.verdict)}>{session.verdict || "IN_PROGRESS"}</span>
              <span className="small">{session.created_at?.slice(0, 10)}</span>
            </div>
            <div className="small">
              Rounds: {session.total_rounds || 0} · Fixed: {session.total_issues_fixed || 0}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
