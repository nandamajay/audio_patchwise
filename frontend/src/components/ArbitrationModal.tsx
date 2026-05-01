import React from "react";

interface ArbitrationModalProps {
  data: {
    issue_id: string;
    chanakya_position: string;
    aryabhata_position: string;
    evidence_summary: any;
  };
  onDecide: (
    decision: "accept_chanakya" | "accept_aryabhata",
    issueId: string,
  ) => void;
}

export const ArbitrationModal: React.FC<ArbitrationModalProps> = ({
  data,
  onDecide,
}) => {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
          border: "1px solid rgba(255,255,255,0.15)",
          borderRadius: "16px",
          padding: "24px",
          maxWidth: "600px",
          width: "90%",
          boxShadow: "0 25px 50px rgba(0,0,0,0.5)",
        }}
      >
        <h3
          style={{
            color: "#f59e0b",
            margin: "0 0 8px",
            fontSize: "18px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          User Arbitration Required
        </h3>
        <p style={{ color: "#9ca3af", fontSize: "13px", margin: "0 0 20px" }}>
          CHANAKYA and ARYABHATA reached a deadlock on Issue #{data.issue_id}.
          Your decision is needed.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          <div
            style={{
              background: "rgba(59,130,246,0.1)",
              border: "1px solid rgba(59,130,246,0.3)",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <div
              style={{
                color: "#60a5fa",
                fontWeight: 700,
                marginBottom: "8px",
                fontSize: "13px",
              }}
            >
              CHANAKYA says:
            </div>
            <div style={{ color: "#e2e8f0", fontSize: "12px", lineHeight: "1.5" }}>
              {data.chanakya_position}
            </div>
            <button
              onClick={() => onDecide("accept_chanakya", data.issue_id)}
              style={{
                marginTop: "12px",
                width: "100%",
                background: "rgba(59,130,246,0.2)",
                border: "1px solid rgba(59,130,246,0.4)",
                borderRadius: "8px",
                color: "#93c5fd",
                padding: "8px",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              Accept CHANAKYA&apos;s position
            </button>
          </div>

          <div
            style={{
              background: "rgba(139,92,246,0.1)",
              border: "1px solid rgba(139,92,246,0.3)",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <div
              style={{
                color: "#a78bfa",
                fontWeight: 700,
                marginBottom: "8px",
                fontSize: "13px",
              }}
            >
              ARYABHATA says:
            </div>
            <div style={{ color: "#e2e8f0", fontSize: "12px", lineHeight: "1.5" }}>
              {data.aryabhata_position}
            </div>
            <button
              onClick={() => onDecide("accept_aryabhata", data.issue_id)}
              style={{
                marginTop: "12px",
                width: "100%",
                background: "rgba(139,92,246,0.2)",
                border: "1px solid rgba(139,92,246,0.4)",
                borderRadius: "8px",
                color: "#c4b5fd",
                padding: "8px",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              Accept ARYABHATA&apos;s position
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ArbitrationModal;
