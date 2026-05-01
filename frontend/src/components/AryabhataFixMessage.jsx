import React, { useState } from "react";

import { MonacoDiffInline } from "./MonacoDiffInline";

export const AryabhataFixMessage = ({ message, onFeedback = () => undefined }) => {
  const [expandedFix, setExpandedFix] = useState(null);
  const [showFullDiff, setShowFullDiff] = useState(false);
  const [showJustification, setShowJustification] = useState(false);
  const [showFixedPatch, setShowFixedPatch] = useState(false);

  const fixes = message.fix_summary || [];
  const diff = message.diff_from_previous || "";

  return (
    <div className="aryabhata-message">
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
        <span style={{ fontSize: "14px", fontWeight: "600", color: "#c4b5fd" }}>
          Applied {fixes.length} fix{fixes.length !== 1 ? "es" : ""}
        </span>
        {message.validation_passed ? (
          <span className="badge" style={{ background: "rgba(34,197,94,0.2)", color: "#86efac" }}>
            Validated
          </span>
        ) : null}
      </div>

      {fixes.map((fix) => (
        <div
          key={fix.issue_id}
          style={{
            background: "rgba(139,92,246,0.05)",
            border: "1px solid rgba(139,92,246,0.2)",
            borderRadius: "6px",
            padding: "10px",
            marginBottom: "8px",
          }}
        >
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span className="badge" style={{ background: "#7c3aed", fontSize: "10px" }}>
              #{fix.issue_id}
            </span>
            <span className="badge" style={{ background: "rgba(139,92,246,0.2)", fontSize: "10px" }}>
              {fix.category}
            </span>
            <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#9ca3af" }}>
              Line {fix.line}
            </span>
            <span
              className="badge"
              style={{
                background: "rgba(34,197,94,0.15)",
                color: "#86efac",
                marginLeft: "auto",
                fontSize: "10px",
              }}
            >
              {fix.status}
            </span>
          </div>

          <div style={{ marginTop: "8px", fontSize: "12px", color: "#fca5a5", fontFamily: "monospace" }}>
            Was: {fix.problem}
          </div>
          <div style={{ marginTop: "4px", fontSize: "12px", color: "#86efac", fontFamily: "monospace" }}>
            Fix: {fix.fix}
          </div>

          <div style={{ marginTop: "8px", display: "flex", gap: "8px" }}>
            <button
              type="button"
              className="btn secondary"
              onClick={() => setExpandedFix(expandedFix === fix.issue_id ? null : fix.issue_id)}
            >
              {expandedFix === fix.issue_id ? "Hide Diff" : "Show Diff"}
            </button>
          </div>

          {expandedFix === fix.issue_id ? (
            <div style={{ marginTop: "8px" }}>
              <MonacoDiffInline original={fix.problem} modified={fix.fix} lineNumber={fix.line} />
            </div>
          ) : null}
        </div>
      ))}

      <div style={{ marginTop: "12px", display: "flex", gap: "8px" }}>
        <button type="button" className="btn secondary" onClick={() => setShowFullDiff((prev) => !prev)}>
          {showFullDiff ? "Hide Full Patch Diff" : "View Full Patch Diff"}
        </button>
        <button type="button" className="btn secondary" onClick={() => setShowFixedPatch((prev) => !prev)}>
          {showFixedPatch ? "Hide Fixed Patch" : "Show Fixed Patch"}
        </button>
        <button type="button" className="btn secondary" onClick={() => setShowJustification((prev) => !prev)}>
          {showJustification ? "Hide Justification" : "Show Justification"}
        </button>
      </div>

      {showFixedPatch && message.fixed_patch ? (
        <div
          style={{
            marginTop: "8px",
            fontFamily: "monospace",
            fontSize: "11px",
            background: "rgba(0,0,0,0.45)",
            padding: "12px",
            borderRadius: "6px",
            maxHeight: "240px",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            color: "#c4b5fd",
          }}
        >
          {"<<<FIXED_PATCH_START>>>\n"}
          {message.fixed_patch}
          {"\n<<<FIXED_PATCH_END>>>"}
        </div>
      ) : null}

      {showFullDiff && diff ? (
        <div
          style={{
            marginTop: "8px",
            fontFamily: "monospace",
            fontSize: "11px",
            background: "rgba(0,0,0,0.4)",
            padding: "12px",
            borderRadius: "6px",
            maxHeight: "200px",
            overflow: "auto",
            whiteSpace: "pre",
          }}
        >
          {diff.split("\n").map((line, index) => (
            <div
              key={`${line}-${index}`}
              style={{
                color: line.startsWith("+")
                  ? "#86efac"
                  : line.startsWith("-")
                    ? "#fca5a5"
                    : line.startsWith("@@")
                      ? "#60a5fa"
                      : "#9ca3af",
              }}
            >
              {line}
            </div>
          ))}
        </div>
      ) : null}

      {showJustification && message.justification ? (
        <div
          style={{
            marginTop: "8px",
            fontSize: "12px",
            color: "#d1d5db",
            background: "rgba(139,92,246,0.05)",
            padding: "10px",
            borderRadius: "6px",
            lineHeight: "1.6",
          }}
        >
          {message.justification}
        </div>
      ) : null}

      <div
        style={{
          marginTop: "12px",
          display: "flex",
          gap: "8px",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          paddingTop: "10px",
        }}
      >
        <button type="button" className="btn secondary" onClick={() => onFeedback(message.id, "up")}>
          Helpful
        </button>
        <button type="button" className="btn secondary" onClick={() => onFeedback(message.id, "down")}>
          Not Helpful
        </button>
      </div>
    </div>
  );
};

export default AryabhataFixMessage;
