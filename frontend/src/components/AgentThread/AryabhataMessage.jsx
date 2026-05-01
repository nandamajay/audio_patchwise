import { useState } from "react";
import { DiffEditor as MonacoDiffEditor } from "@monaco-editor/react";

export default function AryabhataMessage({ message }) {
  const [expanded, setExpanded] = useState(false);

  if (message.type !== "FIX_APPLIED") return null;

  return (
    <div className="fix-diff-container glass" style={{ padding: 10, borderRadius: 10, marginTop: 8 }}>
      <div className="diff-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="diff-badge applied">✅ Fix Applied</span>
        <span className="issue-ref">Issue #{message.metadata?.issue_ref || "unknown"}</span>
        <button type="button" className="btn secondary" onClick={() => setExpanded((prev) => !prev)}>
          {expanded ? "▲ Collapse" : "▼ Show Diff"}
        </button>
      </div>

      {expanded ? (
        <div style={{ marginTop: 8 }}>
          <MonacoDiffEditor
            original={message.metadata?.original_code || ""}
            modified={message.metadata?.fixed_code || ""}
            language="c"
            theme="vs-dark"
            height="200px"
            options={{ readOnly: true, renderSideBySide: true }}
          />
        </div>
      ) : null}
    </div>
  );
}
