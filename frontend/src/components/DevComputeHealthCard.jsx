import React, { useEffect, useState } from "react";

export function DevComputeHealthCard() {
  const [status, setStatus] = useState(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [screens, setScreens] = useState([]);

  const fetchStatus = async () => {
    try {
      const [statusRes, screensRes] = await Promise.all([
        fetch("/api/dev-compute/health"),
        fetch("/api/dev-compute/screens"),
      ]);
      const statusData = await statusRes.json();
      const screensData = await screensRes.json();
      setStatus(statusData);
      setScreens(screensData.screens || []);
    } catch {
      setStatus({ status: "unreachable", mode: "local_docker" });
    }
  };

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 15000);
    return () => clearInterval(timer);
  }, []);

  const handleReconnect = async () => {
    setReconnecting(true);
    try {
      await fetch("/api/dev-compute/reconnect", { method: "POST" });
      await fetchStatus();
    } finally {
      setReconnecting(false);
    }
  };

  if (!status) {
    return (
      <div className="health-card loading">
        <span>Checking dev-compute...</span>
      </div>
    );
  }

  const isConnected = status.status === "connected";
  const isFallback = status.mode === "local_docker";
  const isReconnecting = status.status === "reconnecting";

  const chanakyaScreens = screens.filter((s) => s.includes("chanakya")).length;
  const aryabhataScreens = screens.filter((s) => s.includes("aryabhata")).length;

  return (
    <div
      className={`health-card dev-compute-card ${
        isConnected ? "connected" : isFallback ? "fallback" : isReconnecting ? "reconnecting" : "error"
      }`}
      style={{
        marginTop: 16,
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 14,
        padding: 16,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ color: "#fff", fontWeight: 700 }}>Dev-Compute</div>
        <div style={{ color: isConnected ? "#00d68f" : isFallback ? "#ffaa00" : "#ff3d71", fontSize: 12 }}>
          {isConnected ? "Connected" : isFallback ? "Fallback" : isReconnecting ? "Reconnecting" : "Disconnected"}
        </div>
      </div>

      <div style={{ fontSize: 12, color: "#c7d1dc", display: "grid", gap: 6 }}>
        <div>Host: {status.host || "hu-nandam-hyd"}</div>
        <div>Mode: {status.mode || "unknown"}</div>
        <div>Kernel path: {status.kernel_path || "-"}</div>
      </div>

      <div style={{ display: "flex", gap: 12, marginTop: 12, fontSize: 12, color: "#e8eef5" }}>
        <div>CHANAKYA screens: {chanakyaScreens}</div>
        <div>ARYABHATA screens: {aryabhataScreens}</div>
      </div>

      {!isConnected && (
        <button
          type="button"
          onClick={handleReconnect}
          disabled={reconnecting}
          style={{
            marginTop: 12,
            padding: "6px 10px",
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.2)",
            background: "rgba(255,255,255,0.06)",
            color: "#fff",
            cursor: reconnecting ? "not-allowed" : "pointer",
          }}
        >
          {reconnecting ? "Reconnecting..." : "Reconnect"}
        </button>
      )}
    </div>
  );
}
