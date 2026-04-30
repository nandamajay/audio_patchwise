import { useState } from "react";

export default function JustificationCard({ card }) {
  const [open, setOpen] = useState(false);
  if (!card) return null;

  return (
    <div className="glass" style={{ borderRadius: 12, padding: 10, marginTop: 8 }}>
      <button type="button" className="btn secondary" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide" : "Show"} Justification
      </button>
      {open ? (
        <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
          <div><strong>Issue:</strong> {card.issue}</div>
          <div><strong>Root Cause:</strong> {card.root_cause}</div>
          <div><strong>Fix Approach:</strong> {card.fix_approach}</div>
          <div><strong>Why:</strong> {card.why_this_approach}</div>
        </div>
      ) : null}
    </div>
  );
}
