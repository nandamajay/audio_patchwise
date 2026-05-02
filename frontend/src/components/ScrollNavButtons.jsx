import React from "react";

export const ScrollToTop = () => (
  <button
    type="button"
    onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
    style={{
      position: "fixed",
      right: 20,
      bottom: 64,
      zIndex: 210,
      borderRadius: 999,
      border: "1px solid rgba(148,163,184,0.4)",
      background: "rgba(15,23,42,0.85)",
      color: "#e2e8f0",
      padding: "8px 12px",
      cursor: "pointer",
    }}
  >
    Top
  </button>
);

export const ScrollToBottom = () => (
  <button
    type="button"
    onClick={() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" })}
    style={{
      position: "fixed",
      right: 20,
      bottom: 20,
      zIndex: 210,
      borderRadius: 999,
      border: "1px solid rgba(148,163,184,0.4)",
      background: "rgba(15,23,42,0.85)",
      color: "#e2e8f0",
      padding: "8px 12px",
      cursor: "pointer",
    }}
  >
    Latest
  </button>
);

export default function FloatingNavButtons() {
  return (
    <>
      <ScrollToTop />
      <ScrollToBottom />
    </>
  );
}
