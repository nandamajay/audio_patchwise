import React from "react";

export const JointLGTMSummary = ({ summary }) => {
  if (!summary) return null;

  return (
    <div
      style={{
        margin: "12px 16px",
        borderRadius: "12px",
        border: "1px solid rgba(16,185,129,0.3)",
        background: "rgba(16,185,129,0.08)",
        padding: "12px",
      }}
    >
      <div style={{ color: "#34d399", fontWeight: 700, fontFamily: "monospace", fontSize: "12px" }}>
        JointLGTMSummary
      </div>
      <div style={{ color: "#a7f3d0", marginTop: "6px", fontSize: "12px" }}>
        CHANAKYA: {summary.chanakya_verdict || summary.verdict || "LGTM"}
      </div>
      <div style={{ color: "#c4b5fd", marginTop: "2px", fontSize: "12px" }}>
        ARYABHATA: {summary.aryabhata_verdict || "LGTM"}
      </div>
      {summary.token ? (
        <div style={{ marginTop: "8px", color: "#e5e7eb", fontFamily: "monospace", fontSize: "11px" }}>
          approval token: {summary.token}
        </div>
      ) : null}
    </div>
  );
};

export default JointLGTMSummary;
