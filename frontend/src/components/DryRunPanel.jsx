import { useState } from "react";
import { AlertTriangle, CheckCircle, Edit3, Play, Send, XCircle } from "lucide-react";

const statusConfig = {
  pass: { icon: CheckCircle, color: "#00d68f", label: "PASS" },
  fail: { icon: XCircle, color: "#ff3d71", label: "FAIL" },
  warn: { icon: AlertTriangle, color: "#ffaa00", label: "WARN" },
  pending: { icon: null, color: "#8f9bb3", label: "PENDING" },
};

export default function DryRunPanel({ target, config, onCommandExecuted }) {
  const [checks, setChecks] = useState([]);
  const [running, setRunning] = useState(false);
  const [allPass, setAllPass] = useState(false);
  const [command, setCommand] = useState("");
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState(null);

  const runDryRun = async () => {
    setRunning(true);
    setChecks([]);
    setExecResult(null);

    const [dryRes, cmdRes] = await Promise.all([
      fetch("/api/submission/dry-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, config }),
      }).then((response) => response.json()),
      fetch("/api/submission/build-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, config }),
      }).then((response) => response.json()),
    ]);

    setChecks(dryRes.checks || []);
    setAllPass(dryRes.all_pass || false);
    setCommand(cmdRes.command || "");
    setRunning(false);
  };

  const executeCommand = async () => {
    setExecuting(true);
    const result = await fetch("/api/submission/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, cwd: config?.repo_path || "." }),
    }).then((response) => response.json());

    setExecResult(result);
    setExecuting(false);
    if (result.returncode === 0) {
      onCommandExecuted?.(result);
    }
  };

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "16px",
        padding: "24px",
        marginTop: "16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "20px" }}>
        <Play size={18} color="var(--accent-blue)" />
        <span style={{ color: "#fff", fontWeight: 700, fontSize: "15px" }}>Dry Run - Preflight Checks</span>
        <span
          style={{
            background: "rgba(0,183,255,0.15)",
            color: "var(--accent-blue)",
            borderRadius: "6px",
            padding: "2px 10px",
            fontSize: "11px",
            marginLeft: "auto",
            textTransform: "uppercase",
          }}
        >
          {target}
        </span>
      </div>

      <button
        type="button"
        onClick={runDryRun}
        disabled={running}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: "10px",
          border: "none",
          background: running
            ? "rgba(255,255,255,0.05)"
            : "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
          color: "#fff",
          fontWeight: 600,
          cursor: running ? "not-allowed" : "pointer",
          marginBottom: "20px",
          fontSize: "14px",
        }}
      >
        {running ? "Running Preflight Checks..." : "Run Dry Run Validation"}
      </button>

      {checks.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
          {checks.map((check, index) => {
            const cfg = statusConfig[check.status] || statusConfig.pending;
            const Icon = cfg.icon;
            const tone =
              check.status === "pass" ? "0,214,143" : check.status === "fail" ? "255,61,113" : "255,170,0";
            return (
              <div
                key={`${check.name}-${index}`}
                style={{
                  background: `rgba(${tone},0.08)`,
                  border: `1px solid ${cfg.color}33`,
                  borderRadius: "10px",
                  padding: "12px 16px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  {Icon ? <Icon size={16} color={cfg.color} /> : null}
                  <span style={{ color: "#fff", fontWeight: 600, fontSize: "13px" }}>{check.name}</span>
                  <span
                    style={{
                      marginLeft: "auto",
                      background: `${cfg.color}22`,
                      color: cfg.color,
                      borderRadius: "4px",
                      padding: "1px 8px",
                      fontSize: "10px",
                      fontWeight: 700,
                    }}
                  >
                    {cfg.label}
                  </span>
                </div>
                <p style={{ color: "#8f9bb3", fontSize: "12px", margin: "4px 0 0 24px" }}>{check.description}</p>
                <p style={{ color: cfg.color, fontSize: "12px", margin: "2px 0 0 24px" }}>{check.message}</p>
                {check.command_run ? (
                  <code
                    style={{
                      display: "block",
                      background: "rgba(0,0,0,0.3)",
                      color: "#8f9bb3",
                      borderRadius: "4px",
                      padding: "4px 8px",
                      fontSize: "11px",
                      marginTop: "6px",
                      fontFamily: "monospace",
                    }}
                  >
                    {check.command_run}
                  </code>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {command ? (
        <div
          style={{
            background: "rgba(0,0,0,0.3)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "10px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
            <Edit3 size={14} color="var(--accent-purple)" />
            <span style={{ color: "#fff", fontSize: "13px", fontWeight: 600 }}>Submission Command</span>
            <span style={{ color: "#8f9bb3", fontSize: "11px", marginLeft: "auto" }}>
              You can edit this before submitting
            </span>
          </div>
          <textarea
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            style={{
              width: "100%",
              background: "transparent",
              border: "none",
              color: "#00d68f",
              fontFamily: "monospace",
              fontSize: "12px",
              resize: "vertical",
              minHeight: "60px",
              outline: "none",
            }}
          />
        </div>
      ) : null}

      {command ? (
        <button
          type="button"
          onClick={executeCommand}
          disabled={!allPass || executing}
          style={{
            width: "100%",
            padding: "14px",
            borderRadius: "10px",
            border: "none",
            background:
              allPass && !executing
                ? "linear-gradient(135deg, #00d68f, #00b887)"
                : "rgba(255,255,255,0.05)",
            color: allPass ? "#fff" : "#8f9bb3",
            fontWeight: 700,
            cursor: allPass && !executing ? "pointer" : "not-allowed",
            fontSize: "14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
          }}
        >
          <Send size={16} />
          {executing ? "Submitting..." : allPass ? "Submit Patch" : "Fix All Checks First"}
        </button>
      ) : null}

      {execResult ? (
        <div
          style={{
            marginTop: "16px",
            background: execResult.returncode === 0 ? "rgba(0,214,143,0.1)" : "rgba(255,61,113,0.1)",
            border: `1px solid ${execResult.returncode === 0 ? "#00d68f" : "#ff3d71"}44`,
            borderRadius: "10px",
            padding: "12px 16px",
          }}
        >
          <p style={{ color: execResult.returncode === 0 ? "#00d68f" : "#ff3d71", fontWeight: 600, margin: 0 }}>
            {execResult.returncode === 0 ? "Submission Successful" : "Submission Failed"}
          </p>
          <code
            style={{
              color: "#8f9bb3",
              fontSize: "11px",
              display: "block",
              marginTop: "8px",
              whiteSpace: "pre-wrap",
            }}
          >
            {execResult.stdout || execResult.stderr}
          </code>
        </div>
      ) : null}
    </div>
  );
}
