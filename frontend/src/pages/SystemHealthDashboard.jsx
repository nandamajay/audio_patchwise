import { useEffect, useMemo, useState } from "react";
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
  FileDown,
  FileUp,
  Shield,
} from "lucide-react";
import { DevComputeHealthCard } from "../components/DevComputeHealthCard";

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

function CheckboxRow({ checked, onChange, label }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, color: "#d8e1ea", fontSize: 13 }}>
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}

export default function SystemHealthDashboard() {
  const [activeTab, setActiveTab] = useState("health");
  const [health, setHealth] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [schedulePreset, setSchedulePreset] = useState("every_sunday_night");
  const [loading, setLoading] = useState(true);
  const [reseeding, setReseeding] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [updatingSchedule, setUpdatingSchedule] = useState(false);
  const [runningNow, setRunningNow] = useState(false);

  const [profileSummary, setProfileSummary] = useState(null);
  const [summaryUpdatedAt, setSummaryUpdatedAt] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [exportPassword, setExportPassword] = useState("");
  const [importPassword, setImportPassword] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importSummary, setImportSummary] = useState(null);
  const [selected, setSelected] = useState({
    subsystem_rules: true,
    fix_patterns: true,
    maintainer_prefs: true,
    cover_letter_templates: true,
    embeddings: false,
    lkml_cache: false,
  });

  const fetchHealth = async () => {
    setLoading(true);
    const [healthData, schedulerData] = await Promise.all([
      fetch("/api/health/full").then((response) => response.json()),
      fetch("/api/scheduler/status").then((response) => response.json()),
    ]);
    setHealth(healthData);
    setSchedulerStatus(schedulerData);
    setSchedulePreset(schedulerData.current_preset || "every_sunday_night");
    setLoading(false);
  };

  const fetchProfileSummary = async () => {
    setLoadingSummary(true);
    try {
      const data = await fetch("/api/knowledge/profile/summary").then((response) => response.json());
      setProfileSummary(data);
      setSummaryUpdatedAt(new Date().toISOString());
    } finally {
      setLoadingSummary(false);
    }
  };

  useEffect(() => {
    fetchHealth().catch(() => setLoading(false));
    fetchProfileSummary().catch(() => setLoadingSummary(false));
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

  const updateSchedule = async () => {
    setUpdatingSchedule(true);
    await fetch(`/api/scheduler/update?preset=${encodeURIComponent(schedulePreset)}`, {
      method: "POST",
    });
    await fetchHealth().catch(() => undefined);
    setUpdatingSchedule(false);
  };

  const runSeedNow = async () => {
    setRunningNow(true);
    await fetch("/api/scheduler/run-now", { method: "POST" });
    setTimeout(() => {
      fetchHealth().catch(() => undefined);
      setRunningNow(false);
    }, 2000);
  };

  const selectedComponents = useMemo(
    () => Object.keys(selected).filter((key) => selected[key]),
    [selected],
  );

  const exportProfile = async () => {
    if (!selectedComponents.length) return;
    setExporting(true);
    try {
      const response = await fetch("/api/knowledge/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subsystem: "alsa-asoc",
          selected_components: selectedComponents,
          password: exportPassword || undefined,
        }),
      });
      if (!response.ok) throw new Error("Export failed");

      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match?.[1] || `patchwise_profile_${Date.now()}.pkb`;

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // no-op
    } finally {
      setExporting(false);
    }
  };

  const importProfile = async () => {
    if (!importFile) return;
    setImporting(true);
    setImportSummary(null);
    try {
      const form = new FormData();
      form.append("file", importFile);
      if (importPassword) form.append("password", importPassword);

      const response = await fetch("/api/knowledge/import", {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Import failed");

      setImportSummary(data.import_summary || null);
      await fetchProfileSummary();
    } catch {
      // no-op
    } finally {
      setImporting(false);
    }
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
      <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "22px" }}>
        <Activity size={24} color="var(--accent-blue)" />
        <div>
          <h1 style={{ color: "#fff", margin: 0, fontSize: "22px", fontWeight: 800 }}>System Health</h1>
          <p style={{ color: "#8f9bb3", margin: 0, fontSize: "12px" }}>
            Last updated: {h.timestamp ? new Date(h.timestamp).toLocaleString() : "N/A"}
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            fetchHealth().catch(() => undefined);
            fetchProfileSummary().catch(() => undefined);
          }}
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

      <DevComputeHealthCard />

      <div style={{ display: "flex", gap: 10, marginBottom: 18 }}>
        <button
          type="button"
          className="btn"
          style={{ opacity: activeTab === "health" ? 1 : 0.75 }}
          onClick={() => setActiveTab("health")}
        >
          Health
        </button>
        <button
          type="button"
          className="btn secondary"
          style={{ opacity: activeTab === "knowledge" ? 1 : 0.75 }}
          onClick={() => setActiveTab("knowledge")}
        >
          Knowledge Profile
        </button>
      </div>

      {activeTab === "health" ? (
        <>
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
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "16px",
              padding: "20px",
              marginBottom: "24px",
              display: "grid",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <Clock size={16} color="var(--accent-blue)" />
              <span style={{ color: "#fff", fontWeight: 700 }}>LKML Scheduler</span>
              <span className="small">
                Next run: {schedulerStatus?.next_run ? new Date(schedulerStatus.next_run).toLocaleString() : "manual"}
              </span>
            </div>

            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
              <select
                className="select"
                style={{ maxWidth: 280 }}
                value={schedulePreset}
                onChange={(event) => setSchedulePreset(event.target.value)}
              >
                {(schedulerStatus?.available_presets || []).map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
              </select>
              <button type="button" className="btn secondary" disabled={updatingSchedule} onClick={updateSchedule}>
                {updatingSchedule ? "Updating..." : "Update Schedule"}
              </button>
              <button type="button" className="btn secondary" disabled={runningNow} onClick={runSeedNow}>
                {runningNow ? "Starting..." : "Run Now"}
              </button>
            </div>

            <div className="small">
              Total runs: {schedulerStatus?.stats?.total_runs || 0} · Successful: {schedulerStatus?.stats?.successful_runs || 0} ·
              Total patches: {schedulerStatus?.stats?.total_patches || 0} · Avg duration: {" "}
              {Number(schedulerStatus?.stats?.avg_duration || 0).toFixed(1)}s
            </div>
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
            </div>
          </div>
        </>
      ) : (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
              marginBottom: 20,
            }}
          >
            <MetricCard
              icon={Shield}
              title="Subsystem Rules"
              color="#4db5ff"
              value={profileSummary?.subsystem_rules || 0}
              subvalue="ASoC subsystem rule patterns"
            />
            <MetricCard
              icon={FileDown}
              title="Fix Patterns"
              color="#8f7cff"
              value={profileSummary?.fix_patterns || 0}
              subvalue="ARYABHATA learned fixes"
            />
            <MetricCard
              icon={ThumbsUp}
              title="Maintainer Prefs"
              color="#00d68f"
              value={profileSummary?.maintainer_prefs || 0}
              subvalue="CHANAKYA learned maintainer preferences"
            />
            <MetricCard
              icon={Database}
              title="LKML Cache"
              color="#ffaa00"
              value={(profileSummary?.lkml_cache || 0).toLocaleString()}
              subvalue={`Last updated: ${summaryUpdatedAt ? new Date(summaryUpdatedAt).toLocaleString() : "N/A"}`}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "16px",
                padding: "20px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <FileDown size={16} color="var(--accent-blue)" />
                <span style={{ color: "#fff", fontWeight: 700 }}>Export Profile (.pkb)</span>
              </div>

              <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
                <CheckboxRow
                  checked={selected.subsystem_rules}
                  onChange={(event) => setSelected((prev) => ({ ...prev, subsystem_rules: event.target.checked }))}
                  label="Subsystem Rules (ASoC patterns)"
                />
                <CheckboxRow
                  checked={selected.fix_patterns}
                  onChange={(event) => setSelected((prev) => ({ ...prev, fix_patterns: event.target.checked }))}
                  label="Fix Patterns (ARYABHATA learned fixes)"
                />
                <CheckboxRow
                  checked={selected.maintainer_prefs}
                  onChange={(event) => setSelected((prev) => ({ ...prev, maintainer_prefs: event.target.checked }))}
                  label="Maintainer Preferences"
                />
                <CheckboxRow
                  checked={selected.cover_letter_templates}
                  onChange={(event) =>
                    setSelected((prev) => ({ ...prev, cover_letter_templates: event.target.checked }))
                  }
                  label="Cover Letter Templates"
                />
                <CheckboxRow
                  checked={selected.embeddings}
                  onChange={(event) => setSelected((prev) => ({ ...prev, embeddings: event.target.checked }))}
                  label="ChromaDB Embeddings"
                />
                <CheckboxRow
                  checked={selected.lkml_cache}
                  onChange={(event) => setSelected((prev) => ({ ...prev, lkml_cache: event.target.checked }))}
                  label="LKML Cache"
                />
              </div>

              <input
                className="input"
                type="password"
                placeholder="Optional password"
                value={exportPassword}
                onChange={(event) => setExportPassword(event.target.value)}
              />

              <div style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className="btn"
                  onClick={exportProfile}
                  disabled={exporting || !selectedComponents.length}
                >
                  {exporting ? "Exporting..." : "Export as .pkb"}
                </button>
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
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <FileUp size={16} color="#00d68f" />
                <span style={{ color: "#fff", fontWeight: 700 }}>Import Profile (.pkb)</span>
              </div>

              <label
                style={{
                  border: "1px dashed rgba(255,255,255,0.2)",
                  borderRadius: 10,
                  display: "block",
                  padding: 14,
                  color: "#9cb4c8",
                  marginBottom: 10,
                  cursor: "pointer",
                }}
              >
                <input
                  type="file"
                  accept=".pkb"
                  style={{ display: "none" }}
                  onChange={(event) => setImportFile(event.target.files?.[0] || null)}
                />
                {importFile ? importFile.name : "Drag/drop or click to select .pkb file"}
              </label>

              <input
                className="input"
                type="password"
                placeholder="Password (if encrypted)"
                value={importPassword}
                onChange={(event) => setImportPassword(event.target.value)}
              />

              <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
                <button type="button" className="btn secondary" onClick={importProfile} disabled={importing || !importFile}>
                  {importing ? "Importing..." : "Import .pkb"}
                </button>
                <button type="button" className="btn secondary" onClick={fetchProfileSummary} disabled={loadingSummary}>
                  {loadingSummary ? "Loading..." : "Refresh Summary"}
                </button>
              </div>

              {importSummary ? (
                <div
                  style={{
                    marginTop: 14,
                    background: "rgba(0,214,143,0.08)",
                    border: "1px solid rgba(0,214,143,0.25)",
                    borderRadius: 10,
                    padding: 12,
                    color: "#9ce9cb",
                    fontSize: 13,
                  }}
                >
                  {`Merged ${importSummary.patterns_merged || 0} fix patterns, ${importSummary.rules_merged || 0} subsystem rules, skipped ${importSummary.lkml_skipped_duplicates || 0} duplicate LKML entries.`}
                </div>
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
