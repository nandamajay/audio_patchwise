import { useEffect, useState } from "react";
import { socket } from "../socket";

export interface DriftAlert {
  type: "soft_pause" | "freeze" | "auto_rebased";
  commits_ahead: number;
  affected_files: string[];
  has_conflict: boolean;
  message: string;
  actions?: string[];
}

export function useRebaseMonitor(sessionId: string) {
  const [driftAlert, setDriftAlert] = useState<DriftAlert | null>(null);
  const [rebaseStatus, setRebaseStatus] = useState<"idle" | "rebasing" | "done" | "conflict">("idle");
  const [rebaseStrategy, setRebaseStrategy] = useState<string>("soft_pause");

  useEffect(() => {
    socket.on("drift_detected", setDriftAlert);
    socket.on("rebase_started", () => setRebaseStatus("rebasing"));
    socket.on("rebase_complete", () => {
      setRebaseStatus("done");
      setDriftAlert(null);
    });
    socket.on("rebase_conflict", () => setRebaseStatus("conflict"));

    return () => {
      socket.off("drift_detected");
      socket.off("rebase_started");
      socket.off("rebase_complete");
      socket.off("rebase_conflict");
    };
  }, [sessionId]);

  const triggerAutoRebase = async () => {
    await fetch("/api/rebase/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, target_ref: "origin/master" }),
    });
  };

  const updateStrategy = async (strategy: string) => {
    setRebaseStrategy(strategy);
    await fetch("/api/rebase/set-strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, strategy }),
    });
  };

  return {
    driftAlert,
    rebaseStatus,
    rebaseStrategy,
    triggerAutoRebase,
    updateStrategy,
  };
}
