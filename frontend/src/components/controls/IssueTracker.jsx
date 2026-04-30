export default function IssueTracker({ breakdown }) {
  const entries = Object.entries(breakdown || {});
  const total = entries.reduce((acc, [, count]) => acc + Number(count), 0);

  return (
    <div className="glass card">
      <h4 style={{ marginBottom: 8 }}>Live issue tracker</h4>
      <p style={{ marginBottom: 8 }}>Remaining issues: {total}</p>
      <div style={{ display: "grid", gap: 4 }}>
        {entries.length ? entries.map(([type, count]) => (
          <span className="small" key={type}>{type}: {count}</span>
        )) : <span className="small">No findings yet.</span>}
      </div>
    </div>
  );
}
