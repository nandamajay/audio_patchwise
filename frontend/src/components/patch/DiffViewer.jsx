import { MonacoDiffViewer } from "../MonacoDiffViewer";

export default function DiffViewer({
  original,
  modified,
  language = "text/plain",
  height = "500px",
}) {
  return (
    <div className="glass card" style={{ minHeight: 520, padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
        <span className="small">Original Patch</span>
        <span className="small">ARYABHATA Fixed Patch</span>
      </div>
      <MonacoDiffViewer
        original={original || ""}
        modified={modified || ""}
        language={language}
        height={height}
      />
    </div>
  );
}
