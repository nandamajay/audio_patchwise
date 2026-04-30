export default function GradientHeader({ title, subtitle }) {
  return (
    <div
      style={{
        borderRadius: 14,
        padding: 16,
        border: "1px solid var(--glass-border)",
        background:
          "linear-gradient(125deg, rgba(79,158,255,0.22), rgba(155,109,255,0.2), rgba(79,255,176,0.15))",
      }}
    >
      <h2 style={{ marginBottom: 4 }}>{title}</h2>
      {subtitle ? <p className="small">{subtitle}</p> : null}
    </div>
  );
}
