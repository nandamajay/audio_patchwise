import { useState } from "react";

export default function ThinkingCard({ title = "Thinking...", content = "" }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="glass" style={{ borderRadius: 12, padding: 10, marginTop: 8 }}>
      <button type="button" className="btn secondary" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide" : "Show"} {title}
      </button>
      {open ? <p style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{content || "..."}</p> : null}
    </div>
  );
}
