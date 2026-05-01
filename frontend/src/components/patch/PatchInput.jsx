import { useMemo, useState } from "react";

const tabs = ["raw", "file", "gerrit", "lore"];

export default function PatchInput({ value, onChange }) {
  const [activeTab, setActiveTab] = useState("raw");
  const [selectedFileNames, setSelectedFileNames] = useState([]);

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
        <div style={{ display: "grid", gap: 8 }}>
          <input
            className="input"
            type="file"
            accept=".patch,.diff,.txt"
            multiple
            onChange={async (event) => {
              const files = Array.from(event.target.files || []);
              if (!files.length) return;

              setSelectedFileNames(files.map((file) => file.name));

              const contents = await Promise.all(
                files.map(
                  (file) =>
                    new Promise((resolve) => {
                      const reader = new FileReader();
                      reader.onload = () =>
                        resolve(`# FILE: ${file.name}\n${String(reader.result || "")}`);
                      reader.readAsText(file);
                    }),
                ),
              );

              onChange(contents.join("\n\n").trim());
            }}
          />
          {selectedFileNames.length ? (
            <p className="small">
              Selected {selectedFileNames.length} file(s): {selectedFileNames.join(", ")}
            </p>
          ) : null}
        </div>
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
