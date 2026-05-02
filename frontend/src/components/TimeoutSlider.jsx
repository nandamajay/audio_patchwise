import React from "react";

export const TimeoutSlider = ({ timeout = 60, onChange = () => {} }) => (
  <div style={{ margin: "10px 16px", padding: 10, borderRadius: 8, border: "1px solid rgba(148,163,184,0.2)" }}>
    <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6 }}>challenge timeout slider</div>
    <input
      type="range"
      min="10"
      max="300"
      value={timeout}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ width: "100%" }}
    />
    <div style={{ fontSize: 11, color: "#60a5fa", marginTop: 4 }}>timeout: {timeout}s (default 60)</div>
  </div>
);

export default TimeoutSlider;
