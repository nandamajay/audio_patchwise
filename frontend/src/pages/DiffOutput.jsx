import { useEffect, useMemo } from "react";

import DiffViewer from "../components/patch/DiffViewer";
import PatchWiseCard from "../components/patch/PatchWiseCard";
import SubmissionPanel from "../components/SubmissionPanel/SubmissionPanel";
import GlassCard from "../components/layout/GlassCard";
import useSession from "../hooks/useSession";
import useSessionStore from "../store/sessionStore";

export default function DiffOutput() {
  const { fetchLog, fetchPatchOutput, fetchReport } = useSession();
  const { sessionId, originalPatch, currentPatch, report } = useSessionStore();

  useEffect(() => {
    if (!sessionId) return;
    fetchPatchOutput(sessionId).catch(() => undefined);
    fetchReport(sessionId).catch(() => undefined);
  }, [sessionId, fetchPatchOutput, fetchReport]);

  const findingsByRound = useMemo(() => report?.review_findings || [], [report]);

  const exportLog = async () => {
    if (!sessionId) return;
    const data = await fetchLog(sessionId);
    const text = JSON.stringify(data.conversation_log || [], null, 2);
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `patchwise-${sessionId}-conversation.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid" style={{ gap: 16 }}>
      <DiffViewer original={originalPatch} modified={currentPatch} />

      <GlassCard>
        <h3 style={{ marginBottom: 10 }}>Review Report</h3>
        {!findingsByRound.length ? <p className="small">No report yet.</p> : null}
        {findingsByRound.map((roundItem) => (
          <details key={`report-round-${roundItem.round}`} style={{ marginBottom: 10 }}>
            <summary>
              Round {roundItem.round} — {roundItem.summary || "findings"} — quality {roundItem.quality_score}
            </summary>
            <div style={{ marginTop: 8 }}>
              {(roundItem.findings || []).map((finding, index) => (
                <PatchWiseCard key={`${roundItem.round}-${index}`} finding={finding} />
              ))}
            </div>
          </details>
        ))}
        <button type="button" className="btn secondary" onClick={exportLog}>
          Export conversation log
        </button>
      </GlassCard>

      <SubmissionPanel />
    </div>
  );
}
