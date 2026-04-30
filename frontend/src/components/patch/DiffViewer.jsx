import { DiffEditor } from "@monaco-editor/react";

export default function DiffViewer({ original, modified }) {
  return (
    <div className="glass card" style={{ minHeight: 420 }}>
      <DiffEditor
        height="400px"
        language="diff"
        original={original || ""}
        modified={modified || ""}
        options={{
          renderSideBySide: true,
          readOnly: true,
          minimap: { enabled: false },
          fontSize: 13,
        }}
      />
    </div>
  );
}
