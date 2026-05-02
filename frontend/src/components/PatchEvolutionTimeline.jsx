import React, { useEffect, useMemo, useRef, useState } from "react";
import * as monaco from "monaco-editor";

export const PatchEvolutionTimeline = ({ sessionId, rounds }) => {
  const [selectedRound, setSelectedRound] = useState(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareFrom, setCompareFrom] = useState(0);
  const [compareTo, setCompareTo] = useState(null);
  const diffRef = useRef(null);
  const diffEditorRef = useRef(null);

  const timelineEntries = useMemo(() => {
    const rows = [
      {
        round: 0,
        label: "Original",
        patch: rounds?.[0]?.original_patch || "",
        stats: null,
      },
      ...((rounds || []).map((r, i) => ({
        round: i + 1,
        label: `Round ${i + 1}`,
        patch: r.fixed_patch || r.current_patch || "",
        stats: r.stats || null,
        verdict: r.verdict || null,
      }))),
    ];
    return rows.filter((entry) => entry.patch);
  }, [rounds]);

  useEffect(() => {
    if (timelineEntries.length > 0 && selectedRound === null) {
      setSelectedRound(timelineEntries.length - 1);
      setCompareTo(timelineEntries.length - 1);
    }
  }, [timelineEntries, selectedRound]);

  useEffect(() => {
    if (!diffRef.current) return undefined;

    if (diffEditorRef.current) {
      const models = diffEditorRef.current.getModel();
      diffEditorRef.current.setModel(null);
      if (models) {
        models.original?.dispose();
        models.modified?.dispose();
      }
      diffEditorRef.current.dispose();
      diffEditorRef.current = null;
    }

    const toIndex = compareMode ? (compareTo ?? selectedRound ?? 0) : (selectedRound ?? 0);
    const fromIndex = compareMode ? (compareFrom ?? 0) : Math.max(0, (selectedRound ?? 0) - 1);
    const sourcePatch = timelineEntries[fromIndex]?.patch || "";
    const targetPatch = timelineEntries[toIndex]?.patch || "";

    const originalModel = monaco.editor.createModel(sourcePatch, "diff");
    const modifiedModel = monaco.editor.createModel(targetPatch, "diff");

    diffEditorRef.current = monaco.editor.createDiffEditor(diffRef.current, {
      readOnly: true,
      automaticLayout: true,
      renderSideBySide: true,
      minimap: { enabled: false },
      fontSize: 12,
      lineNumbers: "on",
      scrollBeyondLastLine: false,
      wordWrap: "on",
    });
    diffEditorRef.current.setModel({ original: originalModel, modified: modifiedModel });

    return () => {
      if (!diffEditorRef.current) return;
      const models = diffEditorRef.current.getModel();
      diffEditorRef.current.setModel(null);
      if (models) {
        models.original?.dispose();
        models.modified?.dispose();
      }
      diffEditorRef.current.dispose();
      diffEditorRef.current = null;
    };
  }, [timelineEntries, selectedRound, compareMode, compareFrom, compareTo]);

  if (!sessionId || timelineEntries.length === 0) return null;

  const qualityGauge = timelineEntries.map((entry, idx) => {
    const issuesFixed = Number(entry.stats?.issues_fixed || 0);
    return Math.min(100, idx === 0 ? 0 : (idx * 20) + Math.min(30, issuesFixed * 5));
  });

  return (
    <div
      style={{
        margin: "12px 16px",
        border: "1px solid rgba(148,163,184,0.2)",
        borderRadius: "12px",
        overflow: "hidden",
        background: "rgba(2,8,23,0.85)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 12px",
          borderBottom: "1px solid rgba(148,163,184,0.15)",
        }}
      >
        <div style={{ color: "#cbd5e1", fontFamily: "monospace", fontSize: "12px", fontWeight: 700 }}>
          PatchEvolution - round diff evolution track
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: "6px", color: "#94a3b8", fontSize: "11px" }}>
          <input type="checkbox" checked={compareMode} onChange={(e) => setCompareMode(e.target.checked)} />
          Compare mode
        </label>
      </div>

      <div style={{ padding: "8px 12px", borderBottom: "1px solid rgba(148,163,184,0.15)" }}>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {timelineEntries.map((entry, idx) => (
            <button
              key={`${entry.label}-${idx}`}
              onClick={() => setSelectedRound(idx)}
              style={{
                padding: "4px 8px",
                borderRadius: "6px",
                border: idx === selectedRound ? "1px solid #60a5fa" : "1px solid rgba(148,163,184,0.2)",
                background: idx === selectedRound ? "rgba(96,165,250,0.15)" : "rgba(15,23,42,0.6)",
                color: idx === selectedRound ? "#93c5fd" : "#94a3b8",
                fontSize: "11px",
                cursor: "pointer",
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {compareMode ? (
          <div style={{ display: "flex", gap: "10px", marginTop: "8px", alignItems: "center", color: "#94a3b8" }}>
            <span style={{ fontSize: "11px" }}>From</span>
            <select value={compareFrom ?? 0} onChange={(e) => setCompareFrom(Number(e.target.value))}>
              {timelineEntries.map((entry, idx) => (
                <option key={`from-${idx}`} value={idx}>
                  {entry.label}
                </option>
              ))}
            </select>
            <span style={{ fontSize: "11px" }}>To</span>
            <select value={compareTo ?? selectedRound ?? 0} onChange={(e) => setCompareTo(Number(e.target.value))}>
              {timelineEntries.map((entry, idx) => (
                <option key={`to-${idx}`} value={idx}>
                  {entry.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div style={{ marginTop: "10px" }}>
          <div style={{ color: "#64748b", fontSize: "10px", marginBottom: "4px" }}>Patch qualityGauge per round</div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", height: "28px" }}>
            {qualityGauge.map((q, i) => (
              <div key={`q-${i}`} style={{ width: "16px", height: `${Math.max(3, q / 4)}px`, background: "#22c55e88" }} />
            ))}
          </div>
        </div>
      </div>

      <div ref={diffRef} style={{ height: "360px" }} />
    </div>
  );
};

export default PatchEvolutionTimeline;
