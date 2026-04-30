export default function RoundTracker({ current = 1, max = 5, history = [] }) {
  return (
    <div className="glass card">
      <h4 style={{ marginBottom: 8 }}>Rounds</h4>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        {Array.from({ length: max }, (_, index) => index + 1).map((round) => (
          <span
            key={round}
            style={{
              width: 14,
              height: 14,
              borderRadius: 999,
              display: "inline-block",
              border: "1px solid var(--glass-border)",
              background: round <= current ? "var(--accent-blue)" : "transparent",
            }}
          />
        ))}
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {history.length ? history.map((item) => (
          <div key={`round-${item.round}`} className="small">
            Round {item.round}: {item.summary}
          </div>
        )) : <span className="small">Waiting for first review round.</span>}
      </div>
    </div>
  );
}
