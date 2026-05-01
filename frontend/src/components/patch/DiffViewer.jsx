import { MonacoDiffFull } from "../MonacoDiffInline";

export default function DiffViewer({ original, modified }) {
  return (
    <div className="glass card" style={{ minHeight: 520 }}>
      <MonacoDiffFull original={original || ""} modified={modified || ""} />
    </div>
  );
}
