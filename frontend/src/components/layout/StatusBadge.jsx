export default function StatusBadge({ label, tone = "default" }) {
  const tones = {
    default: { color: "var(--text-secondary)", borderColor: "var(--glass-border)" },
    success: { color: "var(--accent-green)", borderColor: "rgba(79,255,176,0.35)" },
    warning: { color: "var(--accent-orange)", borderColor: "rgba(255,179,71,0.35)" },
    danger: { color: "#ff7f7f", borderColor: "rgba(255,127,127,0.35)" },
  };

  return (
    <span className="badge" style={{ color: tones[tone].color, borderColor: tones[tone].borderColor }}>
      {label}
    </span>
  );
}
