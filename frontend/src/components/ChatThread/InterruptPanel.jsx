export default function InterruptPanel({
  isPaused,
  isAborted,
  hint,
  setHint,
  sendInterrupt,
  sendResume,
  sendAbort,
  roundInfo,
}) {
  if (isAborted) {
    return (
      <div className="glass card" style={{ position: "sticky", bottom: 0 }}>
        <strong>🛑 Session aborted</strong>
      </div>
    );
  }

  if (!isPaused) {
    return (
      <div className="glass card" style={{ position: "sticky", bottom: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>💬 Agents are working... {roundInfo}</span>
        <button type="button" className="btn secondary" style={{ borderColor: "rgba(255,179,71,0.4)", color: "#ffb347" }} onClick={() => sendInterrupt(hint)}>
          ⏸ Pause & Guide
        </button>
      </div>
    );
  }

  return (
    <div className="glass card" style={{ position: "sticky", bottom: 0 }}>
      <strong>⏸ Session Paused</strong>
      <textarea
        className="textarea"
        style={{ marginTop: 8 }}
        value={hint}
        placeholder="💡 Enter your hint for the agents (optional)..."
        onChange={(event) => setHint(event.target.value)}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" className="btn" style={{ flex: 1, boxShadow: "0 0 16px rgba(79,255,176,0.35)" }} onClick={sendResume}>
          ▶ Resume with hint
        </button>
        <button type="button" className="btn secondary" style={{ flex: 1, color: "#ff7f7f", borderColor: "rgba(255,127,127,0.35)" }} onClick={sendAbort}>
          🛑 Abort Session
        </button>
      </div>
    </div>
  );
}
