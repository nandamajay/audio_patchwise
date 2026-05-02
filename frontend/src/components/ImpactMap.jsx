import React, { useState } from "react";

export const ImpactMap = ({ impact = null }) => {
  const [collapsed, setCollapsed] = useState(true);
  if (!impact) return null;
  return (
    <div
      style={{
        margin: "10px 16px",
        borderRadius: 10,
        border: "1px solid rgba(245,158,11,0.35)",
        background: "rgba(245,158,11,0.08)",
      }}
    >
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        style={{
          width: "100%",
          textAlign: "left",
          border: "none",
          background: "transparent",
          color: "#fbbf24",
          padding: "8px 10px",
          cursor: "pointer",
          fontSize: 12,
        }}
      >
        ImpactMap (impact chain viz) - {collapsed ? "collapsed" : "open"}
      </button>
      {collapsed ? null : (
        <pre style={{ margin: 0, padding: "0 10px 10px", color: "#fcd34d", fontSize: 11, whiteSpace: "pre-wrap" }}>
          {JSON.stringify(impact, null, 2)}
        </pre>
      )}
    </div>
  );
};

export default ImpactMap;
