import { useMemo, useState } from "react";

const checks = [
  { key: "style", label: "Style clean" },
  { key: "logic", label: "Logic verified" },
  { key: "memory", label: "Memory safe" },
  { key: "lkml", label: "LKML compliant" },
];

export default function ApprovalGate() {
  const [state, setState] = useState({ style: false, logic: false, memory: false, lkml: false });
  const [target, setTarget] = useState("download");

  const ready = useMemo(() => Object.values(state).every(Boolean), [state]);

  return (
    <div className="glass card">
      <h3 style={{ marginBottom: 10 }}>Approval Gate</h3>
      <div style={{ display: "grid", gap: 6, marginBottom: 12 }}>
        {checks.map((item) => (
          <label key={item.key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={state[item.key]}
              onChange={(event) => setState((prev) => ({ ...prev, [item.key]: event.target.checked }))}
            />
            {item.label}
          </label>
        ))}
      </div>
      <select className="select" value={target} onChange={(event) => setTarget(event.target.value)}>
        <option value="gerrit">Gerrit</option>
        <option value="github">GitHub</option>
        <option value="upstream">Upstream (email patch)</option>
        <option value="download">Download only</option>
      </select>
      <button
        type="button"
        className="btn"
        style={{ marginTop: 10, width: "100%", opacity: ready ? 1 : 0.6 }}
        disabled={!ready}
        onClick={() => window.alert(`Confirmed submit target: ${target}`)}
      >
        Approve & Submit
      </button>
    </div>
  );
}
