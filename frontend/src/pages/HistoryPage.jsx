import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { DiffEditor } from "@monaco-editor/react";
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import useHistoryStore from "../stores/historyStore";

const PIE_COLORS = ["#4f9eff", "#4fffb0", "#ffb347", "#ff7f7f"];

function verdictEmoji(verdict) {
  if (verdict === "LGTM") return "✅";
  if (verdict === "MAX_ROUNDS") return "⚠️";
  if (verdict === "INTERRUPTED") return "🔄";
  return "🕒";
}

export default function HistoryPage() {
  const location = useLocation();
  const {
    sessions,
    selectedSession,
    replayData,
    replayIndex,
    isReplaying,
    replaySpeed,
    globalStats,
    analytics,
    filters,
    search,
    activeTab,
    fetchSessions,
    fetchGlobalStats,
    selectSession,
    startReplay,
    pauseReplay,
    rewindReplay,
    setReplaySpeed,
    setReplayIndex,
    setActiveTab,
    setSearch,
    setFilters,
    exportSession,
    deleteSession,
  } = useHistoryStore();

  const [selectedRound, setSelectedRound] = useState(1);

  useEffect(() => {
    fetchSessions().catch(() => undefined);
    fetchGlobalStats().catch(() => undefined);
  }, [fetchSessions, fetchGlobalStats]);

  useEffect(() => {
    const preselected = location.state?.sessionId;
    if (preselected) {
      selectSession(preselected).catch(() => undefined);
    }
  }, [location.state, selectSession]);

  const replayMessages = useMemo(() => {
    const messages = replayData?.messages || [];
    return messages.slice(0, Math.max(0, replayIndex));
  }, [replayData, replayIndex]);

  const roundData = useMemo(() => replayData?.rounds || [], [replayData]);

  useEffect(() => {
    if (!roundData.length) return;
    setSelectedRound(roundData[0].round_number || 1);
  }, [roundData]);

  const selectedRoundData = useMemo(
    () => roundData.find((item) => item.round_number === selectedRound) || null,
    [roundData, selectedRound],
  );

  const pieData = useMemo(() => {
    const rounds = analytics?.rounds_detail || [];
    const found = rounds.reduce((sum, item) => sum + (item.issues_found || 0), 0);
    const fixed = rounds.reduce((sum, item) => sum + (item.issues_fixed || 0), 0);
    const remaining = Math.max(0, found - fixed);
    return [
      { name: "Fixed", value: fixed },
      { name: "Remaining", value: remaining },
    ];
  }, [analytics]);

  const maxReplay = replayData?.messages?.length || 0;

  return (
    <div className="history-layout">
      <aside className="glass card history-left">
        <h3>🕐 PatchWise History</h3>
        <input
          className="input"
          style={{ marginTop: 10 }}
          placeholder="Search patches..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onBlur={() => fetchSessions().catch(() => undefined)}
        />

        <div className="grid" style={{ gap: 8, marginTop: 10 }}>
          <select
            className="select"
            value={filters.subsystem}
            onChange={(event) => setFilters({ subsystem: event.target.value })}
            onBlur={() => fetchSessions().catch(() => undefined)}
          >
            <option value="">All subsystems</option>
            <option value="audio">audio</option>
            <option value="ASoC">ASoC</option>
            <option value="network">network</option>
            <option value="gpu">gpu</option>
          </select>

          <select
            className="select"
            value={filters.verdict}
            onChange={(event) => setFilters({ verdict: event.target.value })}
            onBlur={() => fetchSessions().catch(() => undefined)}
          >
            <option value="">All verdicts</option>
            <option value="LGTM">LGTM</option>
            <option value="MAX_ROUNDS">MAX_ROUNDS</option>
            <option value="INTERRUPTED">INTERRUPTED</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
          </select>

          <input
            className="input"
            type="date"
            value={filters.date_from}
            onChange={(event) => setFilters({ date_from: event.target.value })}
            onBlur={() => fetchSessions().catch(() => undefined)}
          />
          <input
            className="input"
            type="date"
            value={filters.date_to}
            onChange={(event) => setFilters({ date_to: event.target.value })}
            onBlur={() => fetchSessions().catch(() => undefined)}
          />
          <button type="button" className="btn secondary" onClick={() => fetchSessions().catch(() => undefined)}>
            Apply Filters
          </button>
        </div>

        <div className="glass" style={{ marginTop: 12, padding: 10, borderRadius: 10 }}>
          <h4>Global Stats</h4>
          <p className="small">Total: {globalStats?.total_sessions || 0}</p>
          <p className="small">LGTM: {globalStats?.lgtm_sessions || 0}</p>
          <p className="small">Avg Rounds: {globalStats?.avg_rounds_to_lgtm || 0}</p>
          <p className="small">KB Contrib: {globalStats?.kb_contributions || 0}</p>
        </div>

        <div className="history-session-list">
          {sessions.map((session) => (
            <button
              type="button"
              key={session.id}
              className={`history-session-item ${selectedSession?.id === session.id ? "active" : ""}`}
              onClick={() => selectSession(session.id)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong title={session.title}>{verdictEmoji(session.verdict)} {session.title?.slice(0, 40) || session.id}</strong>
              </div>
              <div className="small">
                {session.subsystem} · {session.total_rounds || 0} rounds · {session.total_issues_fixed || 0} fixed
              </div>
              <div className="small">{session.created_at}</div>
            </button>
          ))}
          {!sessions.length ? <p className="small">No history yet.</p> : null}
        </div>
      </aside>

      <section className="glass card history-right">
        {!selectedSession ? (
          <p className="small">Select a session from the left panel to replay details.</p>
        ) : (
          <>
            <div className="history-header">
              <div>
                <h3>{selectedSession.title}</h3>
                <p className="small">
                  {selectedSession.subsystem} · {selectedSession.total_rounds} rounds · {selectedSession.llm_model} · {selectedSession.created_at}
                </p>
              </div>
              <span className="badge">{verdictEmoji(selectedSession.verdict)} {selectedSession.verdict}</span>
            </div>

            <div className="history-tabs">
              {[
                ["conversation", "💬 Conversation"],
                ["analytics", "📊 Analytics"],
                ["diffs", "🔧 Diffs"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`btn secondary ${activeTab === key ? "active-tab" : ""}`}
                  onClick={() => setActiveTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            {activeTab === "conversation" ? (
              <div className="grid" style={{ gap: 10 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button type="button" className="btn secondary" onClick={startReplay}>▶ Replay</button>
                  <button type="button" className="btn secondary" onClick={pauseReplay}>⏸ Pause</button>
                  <button type="button" className="btn secondary" onClick={rewindReplay}>⏮ Rewind</button>
                  <button type="button" className="btn secondary" onClick={() => setReplaySpeed(replaySpeed === 1 ? 2 : 1)}>
                    {replaySpeed}x
                  </button>
                  <span className="small">{isReplaying ? "Replaying..." : "Paused"}</span>
                </div>

                <input
                  type="range"
                  min="0"
                  max={maxReplay}
                  value={Math.min(replayIndex, maxReplay)}
                  onChange={(event) => setReplayIndex(Number(event.target.value))}
                />

                <div className="history-conversation">
                  {replayMessages.map((message) => (
                    <div key={message.id} className="glass" style={{ padding: 10, borderRadius: 10 }}>
                      <strong>[{message.agent}] {String(message.msg_type || message.type || "message").toUpperCase()}</strong>
                      <p style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{message.content}</p>
                    </div>
                  ))}
                  {!replayMessages.length ? <p className="small">No messages replayed yet.</p> : null}
                </div>
              </div>
            ) : null}

            {activeTab === "analytics" ? (
              <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="glass" style={{ padding: 10, borderRadius: 10, minHeight: 260 }}>
                  <h4>Issues Found vs Fixed</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={analytics?.rounds_detail || []}>
                      <XAxis dataKey="round" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="issues_found" fill="#4f9eff" />
                      <Bar dataKey="issues_fixed" fill="#4fffb0" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="glass" style={{ padding: 10, borderRadius: 10, minHeight: 260 }}>
                  <h4>Issue Breakdown</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={80} label>
                        {pieData.map((entry, idx) => (
                          <Cell key={`${entry.name}-${idx}`} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div className="glass" style={{ padding: 10, borderRadius: 10, minHeight: 260, gridColumn: "1 / -1" }}>
                  <h4>Round Duration</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={analytics?.rounds_detail || []}>
                      <XAxis dataKey="round" />
                      <YAxis />
                      <Tooltip />
                      <Line type="monotone" dataKey="duration_secs" stroke="#ffb347" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : null}

            {activeTab === "diffs" ? (
              <div className="grid" style={{ gap: 10 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {roundData.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`btn secondary ${selectedRound === item.round_number ? "active-tab" : ""}`}
                      onClick={() => setSelectedRound(item.round_number)}
                    >
                      R{item.round_number}
                    </button>
                  ))}
                </div>

                {selectedRoundData ? (
                  <>
                    <div className="small">
                      Round {selectedRoundData.round_number} · Issues {selectedRoundData.issues_found} → {selectedRoundData.issues_fixed}
                    </div>
                    <DiffEditor
                      language="c"
                      theme="vs-dark"
                      height="320px"
                      original={selectedRoundData.chanakya_input || ""}
                      modified={
                        selectedRoundData.aryabhata_output?.fixes?.[0]?.fixed_code ||
                        selectedRoundData.round_diff ||
                        ""
                      }
                      keepCurrentOriginalModel
                      keepCurrentModifiedModel
                      options={{ readOnly: true, renderSideBySide: true }}
                    />
                    {selectedRoundData.round_diff ? (
                      <pre className="history-diff-preview">{selectedRoundData.round_diff}</pre>
                    ) : null}
                  </>
                ) : (
                  <p className="small">No round diff available.</p>
                )}
              </div>
            ) : null}

            <div className="history-export-bar">
              <button type="button" className="btn secondary" onClick={() => exportSession(selectedSession.id, "pdf")}>📄 PDF</button>
              <button type="button" className="btn secondary" onClick={() => exportSession(selectedSession.id, "markdown")}>🗒️ Markdown</button>
              <button type="button" className="btn secondary" onClick={() => exportSession(selectedSession.id, "patch")}>🔧 .patch</button>
              <button type="button" className="btn secondary" onClick={() => exportSession(selectedSession.id, "zip")}>📦 ZIP</button>
              <button
                type="button"
                className="btn secondary"
                onClick={() => deleteSession(selectedSession.id).then(() => fetchSessions())}
              >
                🗑️ Delete
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
