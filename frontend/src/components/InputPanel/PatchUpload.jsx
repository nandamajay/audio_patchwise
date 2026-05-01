import { useState } from "react";
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default function PatchUpload({ onPatchLoaded }) {
  const [selectedFiles, setSelectedFiles] = useState([]);

  const handleMultipleFiles = (event) => {
    const files = Array.from(event.target.files || []);
    setSelectedFiles((prev) => [...prev, ...files]);
  };

  const removeFile = (idx) => {
    setSelectedFiles((prev) => prev.filter((_, index) => index !== idx));
  };

  const uploadFiles = async () => {
    if (!selectedFiles.length) return;
    const formData = new FormData();
    selectedFiles.forEach((file) => formData.append("files[]", file));

    try {
      const response = await api.post("/upload-patches", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const patches = response.data.patches || [];
      const combined = patches
        .map((patch) => `# FILE: ${patch.filename}\n${patch.content}`)
        .join("\n\n")
        .trim();
      onPatchLoaded?.(combined);
    } catch {
      // Fallback to local reads if backend endpoint is unavailable.
      const contents = await Promise.all(
        selectedFiles.map(
          (file) =>
            new Promise((resolve) => {
              const reader = new FileReader();
              reader.onload = () => resolve(`# FILE: ${file.name}\n${String(reader.result || "")}`);
              reader.readAsText(file);
            }),
        ),
      );
      onPatchLoaded?.(contents.join("\n\n"));
    }
  };

  return (
    <div className="glass card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h3>Patch Upload</h3>
        <button type="button" className="btn secondary" onClick={uploadFiles} disabled={!selectedFiles.length}>
          Load {selectedFiles.length || ""} file(s)
        </button>
      </div>
      <input
        type="file"
        accept=".patch,.diff"
        multiple
        onChange={handleMultipleFiles}
        className="input"
      />

      <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
        {selectedFiles.map((file, idx) => (
          <div key={`${file.name}-${idx}`} className="file-chip">
            <span className="patch-icon">📄</span>
            <span>{file.name}</span>
            <span className="file-size">({(file.size / 1024).toFixed(1)}KB)</span>
            <button type="button" onClick={() => removeFile(idx)}>✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}
