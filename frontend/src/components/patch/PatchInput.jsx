import { useMemo, useState } from "react";

const tabs = ["raw", "file", "gerrit", "lore"];

export default function PatchInput({ value, onChange }) {
  const [activeTab, setActiveTab] = useState("raw");

  const helperText = useMemo(() => {
    if (activeTab === "raw") return "Paste patch text directly.";
    if (activeTab === "file") return "Upload .patch file and parse content.";
    if (activeTab === "gerrit") return "Paste Gerrit review URL.";
    return "Paste lore.kernel.org thread URL.";
  }, [activeTab]);

  return (
    <div className="glass card">
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`btn ${tab === activeTab ? "" : "secondary"}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </div>
      <p className="small" style={{ marginBottom: 8 }}>{helperText}</p>
      {activeTab === "file" ? (
        <input
          className="input"
          type="file"
          accept=".patch,.txt"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => onChange(String(reader.result || ""));
            reader.readAsText(file);
          }}
        />
      ) : (
        <textarea
          className="textarea"
          value={value}
          placeholder="Paste patch / link / metadata"
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </div>
  );
}
