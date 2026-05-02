import React, { useEffect, useState } from "react";

export const CoverLetterApprovalCard = ({ draft, onApprove, onEdit, onDismiss }) => {
  const [text, setText] = useState(draft?.draft || "");

  useEffect(() => {
    setText(draft?.draft || "");
  }, [draft]);

  if (!draft) return null;

  return (
    <div
      style={{
        margin: "12px 16px",
        border: "1px solid rgba(245,158,11,0.35)",
        background: "rgba(245,158,11,0.08)",
        borderRadius: "12px",
        padding: "12px",
      }}
    >
      <div style={{ color: "#f59e0b", fontWeight: 700, fontSize: "12px", fontFamily: "monospace" }}>
        Auto-generated cover letter draft
      </div>
      <textarea
        value={text}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          onEdit?.(next);
        }}
        style={{
          marginTop: "8px",
          width: "100%",
          minHeight: "180px",
          borderRadius: "8px",
          border: "1px solid rgba(148,163,184,0.25)",
          background: "rgba(2,6,23,0.65)",
          color: "#e2e8f0",
          fontFamily: "monospace",
          fontSize: "11px",
          padding: "10px",
        }}
      />
      <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
        <button
          type="button"
          onClick={() => onApprove?.(text)}
          style={{
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid #10b98188",
            color: "#10b981",
            background: "rgba(16,185,129,0.12)",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => onDismiss?.()}
          style={{
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid #64748b88",
            color: "#94a3b8",
            background: "rgba(100,116,139,0.12)",
            cursor: "pointer",
          }}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};

export default CoverLetterApprovalCard;
