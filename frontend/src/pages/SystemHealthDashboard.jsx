import { useEffect, useState } from "react";
import {
  Activity,
  BarChart2,
  CheckCircle,
  Clock,
  Database,
  RefreshCw,
  Server,
  ThumbsUp,
  XCircle,
  Zap,
  AlertTriangle,
} from "lucide-react";

const StatusBadge = ({ status }) => {
  const cfg = {
    healthy: { color: "#00d68f", icon: <CheckCircle size={12} />, label: "Healthy" },
    error: { color: "#ff3d71", icon: <XCircle size={12} />, label: "Error" },
    unknown: { color: "#ffaa00", icon: <AlertTriangle size={12} />, label: "Unknown" },
    unavailable: { color: "#ff3d71", icon: <XCircle size={12} />, label: "Down" },
    never_run: { color: "#8f9bb3", icon: <Clock size={12} />, label: "Never Run" },
  }[status] || { color: "#8f9bb3", icon: null, label: status };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "3px 10px",
        borderRadius: "12px",
        background: `${cfg.color}22`,
        color: cfg.color,
        fontSize: "11px",
        fontWeight: 700,
      }}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
};

const MetricCard = ({ icon: Icon, title, value, subvalue, color, action, onAction, loading }) => (
  <div
    style={{
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "16px",
      padding: "20px",
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
      <div
        style={{
          width: "36px",
          height: "36px",
          background: `${color}22`,
          borderRadius: "10px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon size={18} color={color} />
      </div>
      <span style={{ color: "#fff", fontWeight: 700, fontSize: "14px" }}>{title}</span>
      {action ? (
        <button
          type="button"
          onClick={onAction}
          disabled={loading}
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: "4px",
            padding: "5px 12px",
            borderRadius: "8px",
            border: `1px solid ${color}44`,
            background: `${color}11`,
            color,
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: "11px",
            fontWeight: 600,
          }}
        >
          <RefreshCw size={11} className={loading ? "spin" : ""} />
          {loading ? "Running..." : action}
        </button>
      ) : null}
    </div>

    <div style={{ fontSize: "28px", fontWeight: 800, color: "#fff", marginBottom: "4px" }}>{value}</div>
    {subvalue ? <div style={{ fontSize: "12px", color: "#8f9bb3" }}>{subvalue}</div> : null}
  </div>
);

export default function SystemHealthDashboard() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reseeding, setReseeding] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  const fetchHealth = async () => {
    setLoading(true);
    const data = await fetch("/api/health/full").then((response) => response.json());
    setHealth(data);
    setLoading(false);
  };

  useEffect(() => {
    fetchHealth().catch(() => setLoading(false));
  }, []);

  const triggerReseed = async () => {
    setReseeding(true);
    await fetch("/api/health/reseed", { method: "POST" });
    setTimeout(() => {
      setReseeding(false);
      fetchHealth().catch(() => undefined);
    }, 3000);
  };

  const triggerRebuild = async () => {
    setRebuilding(true);
    await fetch("/api/health/rebuild-embeddings", { method: "POST" });
    setTimeout(() => {
      setRebuilding(false);
      fetchHealth().catch(() => undefined);
    }, 3000);
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
        <div style={{ textAlign: "center" }}>
          <Activity size={32} color="var(--accent-blue)" style={{ animation: "spin 1s linear infinite" }} />
          <p style={{ color: "#8f9bb3", marginTop: "12px" }}>Loading system health...</p>
        </div>
      </div>
    );
  }

  const h = health || {};

  return (
    <div style={{ padding: "32px", maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "32px" }}>
        <Activity size={24} color="var(--accent-blue)" />
        <div>
          <h1 style={{ color: "#fff", margin: 0, fontSize: "22px", fontWeight: 800 }}>System Health</h1>
          <p style={{ color: "#8f9bb3", margin: 0, fontSize: "12px" }}>
            Last updated: {h.timestamp ? new Date(h.timestamp).toLocaleString() : "N/A"}
          </p>
        </div>

        <button
          type="button"
          onClick={fetchHealth}
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 16px",
            borderRadius: "10px",
            border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.05)",
            color: "#fff",
            cursor: "pointer",
            fontSize: "13px",
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "16px",
          padding: "16px 20px",
          marginBottom: "24px",
          display: "flex",
          alignItems: "center",
          gap: "24px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ color: "#8f9bb3", fontSize: "12px", fontWeight: 600 }}>SERVICES</span>
        {Object.entries(h.services || {}).map(([name, status]) => (
          <div key={name} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "#fff", fontSize: "13px" }}>{name}</span>
            <StatusBadge status={status} />
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        <MetricCard
          icon={Database}
          title="ChromaDB"
          color="var(--accent-purple)"
          value={`${h.chromadb?.total_vectors?.toLocaleString() || 0} vectors`}
          subvalue={`${h.chromadb?.storage_mb || 0} MB used · ${h.chromadb?.feedback_vectors || 0} feedback vectors`}
          action="Rebuild Embeddings"
          onAction={triggerRebuild}
          loading={rebuilding}
        />

        <MetricCard
          icon={Server}
          title="SQLite Database"
          color="var(--accent-blue)"
          value={`${h.sqlite?.sessions || 0} sessions`}
          subvalue={`${h.sqlite?.patches || 0} patches · ${h.sqlite?.kb_entries || 0} KB entries · ${h.sqlite?.storage_mb || 0} MB`}
        />

        <MetricCard
          icon={Zap}
          title="LKML Pre-Seeder"
          color="#ffaa00"
          value={`${h.lkml_seeder?.patches_fetched?.toLocaleString() || 0} patches`}
          subvalue={`Last run: ${h.lkml_seeder?.last_run ? new Date(h.lkml_seeder.last_run).toLocaleString() : "Never"}`}
          action="Re-seed Now"
          onAction={triggerReseed}
          loading={reseeding}
        />

        <MetricCard
          icon={ThumbsUp}
          title="Feedback Learning"
          color="#00d68f"
          value={`${(h.feedback_stats?.total_upvotes || 0) + (h.feedback_stats?.total_downvotes || 0)} signals`}
          subvalue={`👍 ${h.feedback_stats?.total_upvotes || 0} upvotes · 👎 ${h.feedback_stats?.total_downvotes || 0} downvotes`}
        />
      </div>

      <div
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "16px",
          padding: "20px",
          marginBottom: "24px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
          <BarChart2 size={16} color="var(--accent-blue)" />
          <span style={{ color: "#fff", fontWeight: 700 }}>Agent Performance</span>
        </div>

        <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
          <div>
            <p style={{ color: "#8f9bb3", fontSize: "11px", margin: "0 0 4px 0" }}>AVG ROUNDS TO LGTM</p>
            <p style={{ color: "var(--accent-blue)", fontSize: "24px", fontWeight: 800, margin: 0 }}>
              {h.agent_perf?.avg_rounds_to_lgtm || 0}
            </p>
          </div>
          <div>
            <p style={{ color: "#8f9bb3", fontSize: "11px", margin: "0 0 4px 0" }}>LGTM SESSIONS</p>
            <p style={{ color: "#00d68f", fontSize: "24px", fontWeight: 800, margin: 0 }}>
              {h.agent_perf?.lgtm_sessions || 0}
            </p>
          </div>
          <div>
            <p style={{ color: "#8f9bb3", fontSize: "11px", margin: "0 0 4px 0" }}>MAX ROUNDS HIT</p>
            <p style={{ color: "#ffaa00", fontSize: "24px", fontWeight: 800, margin: 0 }}>
              {h.agent_perf?.max_round_sessions || 0}
            </p>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ color: "#8f9bb3", fontSize: "11px", margin: "0 0 8px 0" }}>TOP ISSUE TYPES</p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {(h.agent_perf?.top_issue_types || []).map((item) => (
                <span
                  key={`${item.type}-${item.count}`}
                  style={{
                    padding: "4px 10px",
                    borderRadius: "8px",
                    background: "rgba(255,255,255,0.05)",
                    color: "#cdd",
                    fontSize: "12px",
                  }}
                >
                  {item.type} <strong style={{ color: "var(--accent-blue)" }}>{item.count}</strong>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "16px",
          padding: "20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
          <ThumbsUp size={16} color="#00d68f" />
          <span style={{ color: "#fff", fontWeight: 700 }}>Top Upvoted Patterns (Leaderboard)</span>
        </div>

        {(h.feedback_stats?.top_patterns || []).length === 0 ? (
          <p style={{ color: "#8f9bb3", fontSize: "13px" }}>
            No feedback yet - upvote/downvote agent suggestions to train the system.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {(h.feedback_stats?.top_patterns || []).map((pattern, index) => (
              <div
                key={`${pattern.agent}-${pattern.issue_type}-${index}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  padding: "10px 14px",
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "10px",
                }}
              >
                <span
                  style={{
                    width: "24px",
                    height: "24px",
                    background:
                      index === 0
                        ? "#ffd700"
                        : index === 1
                          ? "#c0c0c0"
                          : index === 2
                            ? "#cd7f32"
                            : "rgba(255,255,255,0.1)",
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "11px",
                    fontWeight: 800,
                    color: index < 3 ? "#000" : "#8f9bb3",
                  }}
                >
                  {index + 1}
                </span>

                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: "6px",
                    background:
                      pattern.agent === "chanakya" ? "rgba(0,183,255,0.15)" : "rgba(123,47,255,0.15)",
                    color:
                      pattern.agent === "chanakya" ? "var(--accent-blue)" : "var(--accent-purple)",
                    fontSize: "11px",
                    fontWeight: 600,
                    textTransform: "uppercase",
                  }}
                >
                  {pattern.agent}
                </span>

                <span style={{ color: "#8f9bb3", fontSize: "11px" }}>{pattern.issue_type}</span>
                <span
                  style={{
                    flex: 1,
                    color: "#cdd",
                    fontSize: "12px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pattern.sample}
                </span>
                <span
                  style={{
                    color: pattern.net_score >= 0 ? "#00d68f" : "#ff3d71",
                    fontSize: "13px",
                    fontWeight: 700,
                  }}
                >
                  {pattern.net_score >= 0 ? "+" : ""}
                  {pattern.net_score}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
