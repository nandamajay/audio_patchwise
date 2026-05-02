import { useEffect, useMemo, useState } from "react";

const detectSubsystem = (patch) => {
  if (patch.includes("sound/soc") || patch.includes("ALSA") || patch.includes("snd_soc") || patch.includes("ASoC")) return "audio";
  if (patch.includes("drivers/net") || patch.includes("net/wireless")) return "network";
  if (patch.includes("drivers/gpu")) return "gpu";
  return null;
};

const extractKernelVersion = (patch) => {
  const match = patch.match(/Linux kernel (\d+\.\d+)/i) || patch.match(/v(\d+\.\d+\.\d+)/);
  return match ? match[1] : null;
};

const suggestSourcePath = (patch) => {
  const line = patch.split("\n").find((entry) => entry.startsWith("+++ b/"));
  return line ? line.replace("+++ b/", "") : null;
};

export default function ContextBox({ patchContent, value, onChange }) {
  const [contextData, setContextData] = useState({
    subsystem: value.subsystem || "",
    kernelVersion: value.kernelVersion || "",
    sourcePath: value.sourcePath || "",
    notes: value.notes || "",
    autoDetected: false,
  });
  const [pathStatus, setPathStatus] = useState("idle");

  useEffect(() => {
    setContextData((prev) => {
      const next = {
        ...prev,
        subsystem: value.subsystem || "",
        kernelVersion: value.kernelVersion || "",
        sourcePath: value.sourcePath || "",
        notes: value.notes || "",
      };
      if (
        next.subsystem === prev.subsystem &&
        next.kernelVersion === prev.kernelVersion &&
        next.sourcePath === prev.sourcePath &&
        next.notes === prev.notes
      ) {
        return prev;
      }
      return next;
    });
  }, [value.subsystem, value.kernelVersion, value.sourcePath, value.notes]);

  useEffect(() => {
    if (patchContent) {
      const subsystem = detectSubsystem(patchContent);
      const kernelVersion = extractKernelVersion(patchContent);
      const suggestedPath = suggestSourcePath(patchContent);

      setContextData((prev) => ({
        ...prev,
        subsystem: subsystem || prev.subsystem,
        kernelVersion: kernelVersion || prev.kernelVersion,
        sourcePath: suggestedPath || prev.sourcePath,
        autoDetected: true,
      }));
    }
  }, [patchContent]);

  useEffect(() => {
    onChange?.({
      subsystem: contextData.subsystem,
      kernelVersion: contextData.kernelVersion,
      sourcePath: contextData.sourcePath,
      notes: contextData.notes,
    });
  }, [
    contextData.subsystem,
    contextData.kernelVersion,
    contextData.sourcePath,
    contextData.notes,
    onChange,
  ]);

  const helper = useMemo(() => {
    if (contextData.autoDetected) return "Auto-detected from patch content. Adjust if needed.";
    return "Provide subsystem, kernel version, and source path context.";
  }, [contextData.autoDetected]);

  const validateKernelPath = async (path) => {
    try {
      const resp = await fetch("/api/validate-kernel-path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await resp.json();
      setPathStatus(data?.valid ? "valid" : "invalid");
    } catch {
      setPathStatus("invalid");
    }
  };

  return (
    <div className="glass card">
      <h3 style={{ marginBottom: 10 }}>Context</h3>
      <div className="grid" style={{ gap: 8 }}>
        <input
          className="input"
          value={contextData.subsystem}
          placeholder="Subsystem"
          onChange={(event) => setContextData((prev) => ({ ...prev, subsystem: event.target.value }))}
        />
        <input
          className="input"
          value={contextData.kernelVersion}
          placeholder="Kernel version"
          onChange={(event) => setContextData((prev) => ({ ...prev, kernelVersion: event.target.value }))}
        />
        <div style={{ display: "grid", gap: 6 }}>
          <input
            className="input"
            value={contextData.sourcePath}
            placeholder="Kernel source path (optional)"
            onChange={(event) => {
              setContextData((prev) => ({ ...prev, sourcePath: event.target.value }));
              setPathStatus("idle");
            }}
            onBlur={() => contextData.sourcePath && validateKernelPath(contextData.sourcePath)}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              type="button"
              className="btn secondary"
              onClick={() => {
                const next = contextData.sourcePath || "";
                if (next) validateKernelPath(next);
              }}
            >
              Validate Path
            </button>
            <button
              type="button"
              className="btn secondary"
              // browse kernel path
              onClick={async () => {
                if (typeof window.showDirectoryPicker !== "function") {
                  window.alert("Directory picker not supported; paste the path manually.");
                  return;
                }
                try {
                  const handle = await window.showDirectoryPicker();
                  const path = handle?.name ? handle.name : "";
                  if (path) {
                    setContextData((prev) => ({ ...prev, sourcePath: path }));
                    setPathStatus("idle");
                  }
                } catch {
                  // user canceled
                }
              }}
            >
              Browse Kernel Path
            </button>
            {pathStatus === "valid" ? (
              <span className="small" style={{ color: "#86efac" }}>Kernel source found</span>
            ) : null}
            {pathStatus === "invalid" ? (
              <span className="small" style={{ color: "#fca5a5" }}>Path not found</span>
            ) : null}
          </div>
        </div>
      </div>
      {contextData.autoDetected ? <span className="badge auto-detected" style={{ marginTop: 8 }}>✨ Auto-detected from patch</span> : null}
      <p className="small" style={{ marginTop: 8 }}>{helper}</p>

      <textarea
        className="context-input dynamic textarea"
        value={contextData.notes}
        onChange={(event) => setContextData((prev) => ({ ...prev, notes: event.target.value }))}
        placeholder="Any additional context for CHANAKYA & ARYABHATA..."
        style={{ minHeight: "80px", maxHeight: "300px", resize: "vertical", marginTop: 8 }}
      />
    </div>
  );
}
