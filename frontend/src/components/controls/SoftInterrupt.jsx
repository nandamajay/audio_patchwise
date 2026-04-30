import { useState } from "react";

export default function SoftInterrupt({ onSend }) {
  const [hint, setHint] = useState("");

  return (
    <div className="glass card">
      <h4 style={{ marginBottom: 8 }}>💬 Inject a hint</h4>
      <input
        className="input"
        value={hint}
        placeholder="e.g. prioritize memory safety"
        onChange={(event) => setHint(event.target.value)}
      />
      <button
        type="button"
        className="btn"
        style={{ width: "100%", marginTop: 10 }}
        onClick={() => {
          if (!hint.trim()) return;
          onSend?.(hint.trim());
          setHint("");
        }}
      >
        Pause & Guide
      </button>
    </div>
  );
}
