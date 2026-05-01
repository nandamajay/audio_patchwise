import { useEffect, useState } from "react";
import { Mail, Plus, User, Zap } from "lucide-react";

export default function MaintainerSelector({ patchContent, onSelectionChange }) {
  const [allTargets, setAllTargets] = useState({ mailing_lists: [], maintainers: [] });
  const [detected, setDetected] = useState(null);
  const [selectedLists, setSelectedLists] = useState([]);
  const [selectedMaintainers, setSelectedMaintainers] = useState([]);
  const [detecting, setDetecting] = useState(false);
  const [customEmail, setCustomEmail] = useState("");

  useEffect(() => {
    fetch("/api/lkml/all-targets")
      .then((response) => response.json())
      .then((data) => setAllTargets(data || { mailing_lists: [], maintainers: [] }))
      .catch(() => setAllTargets({ mailing_lists: [], maintainers: [] }));
  }, []);

  const emitSelection = (lists, maintainers) => {
    onSelectionChange?.({ lists, maintainers });
  };

  const autoDetect = async () => {
    setDetecting(true);
    const result = await fetch("/api/lkml/auto-detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch_content: patchContent }),
    }).then((response) => response.json());

    setDetected(result);
    const nextListIds = (result.mailing_lists || []).map((item) => item.id);
    const nextMaintainers = (result.maintainers || []).map((item) => item.id);
    setSelectedLists(nextListIds);
    setSelectedMaintainers(nextMaintainers);
    emitSelection(result.mailing_lists || [], result.maintainers || []);
    setDetecting(false);
  };

  const toggleList = (id) => {
    const updated = selectedLists.includes(id)
      ? selectedLists.filter((item) => item !== id)
      : [...selectedLists, id];
    setSelectedLists(updated);

    const selectedListObjects = allTargets.mailing_lists.filter((item) => updated.includes(item.id));
    const selectedMaintainerObjects = allTargets.maintainers.filter((item) =>
      selectedMaintainers.includes(item.id),
    );
    emitSelection(selectedListObjects, selectedMaintainerObjects);
  };

  const toggleMaintainer = (id) => {
    const updated = selectedMaintainers.includes(id)
      ? selectedMaintainers.filter((item) => item !== id)
      : [...selectedMaintainers, id];
    setSelectedMaintainers(updated);

    const selectedListObjects = allTargets.mailing_lists.filter((item) => selectedLists.includes(item.id));
    const selectedMaintainerObjects = allTargets.maintainers.filter((item) => updated.includes(item.id));
    emitSelection(selectedListObjects, selectedMaintainerObjects);
  };

  const addCustomEmail = () => {
    if (!customEmail) return;
    const updated = [...selectedMaintainers, customEmail];
    setSelectedMaintainers(updated);
    setCustomEmail("");

    const selectedListObjects = allTargets.mailing_lists.filter((item) => selectedLists.includes(item.id));
    const selectedMaintainerObjects = [
      ...allTargets.maintainers.filter((item) => updated.includes(item.id)),
      { id: customEmail, name: customEmail, email: customEmail, role: "Custom" },
    ];
    emitSelection(selectedListObjects, selectedMaintainerObjects);
  };

  const chipStyle = (selected) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "6px 12px",
    borderRadius: "20px",
    border: `1px solid ${selected ? "var(--accent-blue)" : "rgba(255,255,255,0.1)"}`,
    background: selected ? "rgba(0,183,255,0.15)" : "rgba(255,255,255,0.05)",
    color: selected ? "var(--accent-blue)" : "#8f9bb3",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: selected ? 600 : 400,
    transition: "all 0.2s",
  });

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "16px",
        padding: "20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
        <Mail size={16} color="var(--accent-blue)" />
        <span style={{ color: "#fff", fontWeight: 700 }}>Mailing Lists & Maintainers</span>
        <button
          type="button"
          onClick={autoDetect}
          disabled={detecting || !patchContent}
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 14px",
            borderRadius: "8px",
            border: "none",
            background: "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
            color: "#fff",
            cursor: detecting || !patchContent ? "not-allowed" : "pointer",
            fontSize: "12px",
            fontWeight: 600,
          }}
        >
          <Zap size={12} />
          {detecting ? "Detecting..." : "Auto-Detect from Patch"}
        </button>
      </div>

      {detected ? (
        <div
          style={{
            background: "rgba(0,214,143,0.08)",
            border: "1px solid rgba(0,214,143,0.2)",
            borderRadius: "8px",
            padding: "8px 12px",
            marginBottom: "14px",
            fontSize: "12px",
            color: "#00d68f",
          }}
        >
          Auto-detected via <strong>{detected.source}</strong> - {detected.mailing_lists?.length || 0} lists, {" "}
          {detected.maintainers?.length || 0} maintainers suggested
        </div>
      ) : null}

      <p style={{ color: "#8f9bb3", fontSize: "12px", marginBottom: "8px" }}>Mailing Lists</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "16px" }}>
        {allTargets.mailing_lists.map((list) => (
          <button key={list.id} type="button" style={chipStyle(selectedLists.includes(list.id))} onClick={() => toggleList(list.id)}>
            <Mail size={10} />
            {list.name}
            {detected?.mailing_lists?.find((item) => item.id === list.id) ? (
              <span
                style={{
                  background: "rgba(0,214,143,0.3)",
                  color: "#00d68f",
                  borderRadius: "4px",
                  padding: "0 4px",
                  fontSize: "9px",
                }}
              >
                AUTO
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <p style={{ color: "#8f9bb3", fontSize: "12px", marginBottom: "8px" }}>Maintainers (CC)</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "16px" }}>
        {allTargets.maintainers.map((maintainer) => (
          <button
            key={maintainer.id}
            type="button"
            style={chipStyle(selectedMaintainers.includes(maintainer.id))}
            onClick={() => toggleMaintainer(maintainer.id)}
          >
            <User size={10} />
            {maintainer.name}
            <span style={{ fontSize: "10px", opacity: 0.7 }}>({maintainer.role})</span>
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "8px" }}>
        <input
          value={customEmail}
          onChange={(event) => setCustomEmail(event.target.value)}
          placeholder="Add custom email..."
          style={{
            flex: 1,
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            padding: "8px 12px",
            color: "#fff",
            fontSize: "12px",
            outline: "none",
          }}
        />
        <button
          type="button"
          onClick={addCustomEmail}
          style={{
            padding: "8px 16px",
            borderRadius: "8px",
            border: "1px solid var(--accent-blue)",
            background: "rgba(0,183,255,0.1)",
            color: "var(--accent-blue)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "12px",
          }}
        >
          <Plus size={12} /> Add
        </button>
      </div>
    </div>
  );
}
