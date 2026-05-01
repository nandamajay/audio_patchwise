import React, { useState } from "react";

import { MonacoDiffInline } from "./MonacoDiffInline";

const CATEGORY_COLORS = {
  STYLE: "#3b82f6",
  LOGIC: "#f59e0b",
  MEMORY: "#ef4444",
  COMMIT: "#8b5cf6",
  COMPLIANCE: "#06b6d4",
};

const SEVERITY_COLORS = {
  CRITICAL: "#ef4444",
  WARNING: "#f59e0b",
  INFO: "#6b7280",
};

export const ReviewIssueCard = ({ issue, onFeedback = () => undefined }) => {
  const [expanded, setExpanded] = useState(false);
  const [showDiff, setShowDiff] = useState(false);

  return (
    <div
      className={`issue-card ${issue.is_recurring ? "recurring" : ""}`}
      style={{
        background: "rgba(255,255,255,0.03)",
        border: `1px solid ${(CATEGORY_COLORS[issue.category] || "#64748b")}40`,
        borderLeft: `3px solid ${SEVERITY_COLORS[issue.severity] || "#6b7280"}`,
        borderRadius: "8px",
        padding: "12px",
        marginTop: "8px",
      }}
    >
      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
        <span className="badge" style={{ background: CATEGORY_COLORS[issue.category] || "#64748b" }}>
          {issue.category}
        </span>

        <span
          className="badge"
          style={{ background: "rgba(255,255,255,0.1)", fontFamily: "monospace", fontSize: "11px" }}
        >
          Line {issue.line_number} · {issue.file_path}
        </span>

        <span
          className="badge"
          style={{
            background: `${SEVERITY_COLORS[issue.severity] || "#6b7280"}30`,
            color: SEVERITY_COLORS[issue.severity] || "#6b7280",
          }}
        >
          {issue.severity}
        </span>

        {issue.is_recurring ? (
          <span
            className="badge"
            style={{ background: "#ef444430", color: "#ef4444", fontWeight: "bold" }}
          >
            Recurring — Round {issue.previous_round}
          </span>
        ) : null}
      </div>

      <div
        style={{
          marginTop: "8px",
          fontFamily: "monospace",
          fontSize: "12px",
          color: "#fca5a5",
          background: "rgba(239,68,68,0.05)",
          padding: "6px 8px",
          borderRadius: "4px",
        }}
      >
        Error: {issue.error_message}
      </div>

      {issue.problematic_code ? (
        <div style={{ marginTop: "8px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
            Problematic Code:
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: "12px",
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.2)",
              padding: "6px 10px",
              borderRadius: "4px",
              color: "#fca5a5",
            }}
          >
            <span style={{ color: "#6b7280" }}>{issue.line_number} | </span>
            {issue.problematic_code}
          </div>
        </div>
      ) : null}

      {issue.suggested_fix ? (
        <div style={{ marginTop: "8px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
            Suggested Fix:
          </div>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: "12px",
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.2)",
              padding: "6px 10px",
              borderRadius: "4px",
              color: "#86efac",
            }}
          >
            <span style={{ color: "#6b7280" }}>{issue.line_number} | </span>
            {issue.suggested_fix}
          </div>
        </div>
      ) : null}

      <div style={{ marginTop: "8px", display: "flex", gap: "8px" }}>
        <button type="button" className="btn secondary" onClick={() => setExpanded((prev) => !prev)}>
          {expanded ? "Hide Context" : "More Context"}
        </button>
        {issue.suggested_fix ? (
          <button type="button" className="btn secondary" onClick={() => setShowDiff((prev) => !prev)}>
            {showDiff ? "Hide Diff" : "Show Diff"}
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div style={{ marginTop: "8px" }}>
          {issue.hunk_context ? (
            <div
              style={{
                fontFamily: "monospace",
                fontSize: "11px",
                background: "rgba(0,0,0,0.3)",
                padding: "8px",
                borderRadius: "4px",
                whiteSpace: "pre",
                marginBottom: "8px",
                overflow: "auto",
                maxHeight: "150px",
              }}
            >
              {issue.hunk_context}
            </div>
          ) : null}

          <p style={{ fontSize: "12px", color: "#d1d5db", lineHeight: "1.6" }}>
            {issue.explanation}
          </p>
          {issue.reference ? (
            <a
              href={issue.reference}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: "11px", color: "#60a5fa", display: "block", marginTop: "4px" }}
            >
              {issue.reference}
            </a>
          ) : null}
        </div>
      ) : null}

      {showDiff && issue.problematic_code && issue.suggested_fix ? (
        <div style={{ marginTop: "8px" }}>
          <MonacoDiffInline
            original={issue.problematic_code}
            modified={issue.suggested_fix}
            lineNumber={issue.line_number}
          />
        </div>
      ) : null}

      <div
        style={{
          marginTop: "10px",
          display: "flex",
          gap: "8px",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          paddingTop: "8px",
        }}
      >
        <button type="button" className="btn secondary" onClick={() => onFeedback(issue.issue_id, "up")}>
          Helpful
        </button>
        <button type="button" className="btn secondary" onClick={() => onFeedback(issue.issue_id, "down")}>
          Not Helpful
        </button>
      </div>
    </div>
  );
};

export default ReviewIssueCard;
