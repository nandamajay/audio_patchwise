import StatusBadge from "../layout/StatusBadge";

export default function PatchWiseCard({ finding }) {
  if (!finding) return null;

  return (
    <div className="glass card" style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <strong>{finding.issue_type}</strong>
        <StatusBadge
          label={finding.severity}
          tone={finding.severity === "CRITICAL" ? "danger" : finding.severity === "WARNING" ? "warning" : "default"}
        />
      </div>
      <p>{finding.description}</p>
      <p className="small" style={{ marginTop: 4 }}>Suggestion: {finding.suggestion}</p>
    </div>
  );
}
