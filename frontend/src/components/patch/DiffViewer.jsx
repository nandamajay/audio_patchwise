import { useRef } from "react";

import { useMonacoDiff } from "../../hooks/useMonacoDiff";

export default function DiffViewer({
  original,
  modified,
  language = "text/plain",
  height = "500px",
}) {
  const containerRef = useRef(null);

  useMonacoDiff(containerRef, {
    originalContent: original || "",
    modifiedContent: modified || "",
    language,
  });

  return (
    <div className="glass card" style={{ minHeight: 520, padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
        <span className="small">Original Patch</span>
        <span className="small">ARYABHATA Fixed Patch</span>
      </div>
      <div
        ref={containerRef}
        style={{
          height,
          width: "100%",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 8,
          overflow: "hidden",
        }}
      />
    </div>
  );
}
