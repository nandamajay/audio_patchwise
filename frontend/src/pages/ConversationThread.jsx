import { useEffect } from "react";
import { Link } from "react-router-dom";

import InterruptPanel from "../components/ChatThread/InterruptPanel";
import AgentStatusBar from "../components/AgentStatusBar";
import CoverLetterApprovalCard from "../components/CoverLetterApprovalCard";
import DevComputePanel from "../components/DevComputePanel";
import HistorySidebar from "../components/HistorySidebar";
import JointLGTMSummary from "../components/JointLGTMSummary";
import NegotiationLog from "../components/NegotiationLog";
import NegotiationStatusBar from "../components/NegotiationStatusBar";
import NegotiationVisualizer from "../components/NegotiationVisualizer";
import PatchEvolutionTimeline from "../components/PatchEvolutionTimeline";
import FloatingNavButtons from "../components/ScrollNavButtons";
import ThreadView from "../components/AgentThread/ConversationThread";
import IssueTracker from "../components/controls/IssueTracker";
import RoundTracker from "../components/controls/RoundTracker";
import SessionHistory from "../components/SessionHistory/SessionHistory";
import GlassCard from "../components/layout/GlassCard";
import useAgentStream from "../hooks/useAgentStream";
import useInterrupt from "../hooks/useInterrupt";
import useSessionStore from "../store/sessionStore";
import { displayRound } from "../store/sessionStore";

export default function ConversationThread() {
  const sessionId = useSessionStore((state) => state.sessionId);
  const currentRound = useSessionStore(displayRound);
  const maxRounds = useSessionStore((state) => state.maxRounds);
  const messages = useSessionStore((state) => state.messages);
  const qualityScore = useSessionStore((state) => state.qualityScore);
  const verdict = useSessionStore((state) => state.verdict);
  const patchwiseNotice = useSessionStore((state) => state.patchwiseNotice);
  const issueBreakdown = useSessionStore((state) => state.issueBreakdown);
  const roundHistory = useSessionStore((state) => state.roundHistory);
  const approvalToken = useSessionStore((state) => state.approvalToken);
  const jointVerdict = useSessionStore((state) => state.jointVerdict);
  const patchEvolutionRounds = useSessionStore((state) => state.patchEvolutionRounds);
  const coverLetterDraft = useSessionStore((state) => state.coverLetterDraft);
  const setCoverLetterDraft = useSessionStore((state) => state.setCoverLetterDraft);
  const devComputeStatus = useSessionStore((state) => state.devComputeStatus);
  const setDevComputeStatus = useSessionStore((state) => state.setDevComputeStatus);
  const setJointVerdict = useSessionStore((state) => state.setJointVerdict);
  const fetchSessions = useSessionStore((state) => state.fetchSessions);

  const { sendEvent } = useAgentStream(sessionId);
  const { isPaused, isAborted, hint, setHint, sendInterrupt, sendResume, sendAbort } = useInterrupt(sessionId, sendEvent);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    let cancelled = false;
    const fetchDevCompute = async () => {
      try {
        const response = await fetch("/api/dev-compute/health");
        const data = await response.json();
        if (cancelled) return;
        setDevComputeStatus({
          ...data,
          status:
            data.status === "connected"
              ? "ssh_connected"
              : data.status === "fallback"
                ? "docker_fallback"
                : "ssh_reconnecting",
        });
      } catch {
        if (!cancelled) {
          setDevComputeStatus({ status: "ssh_disconnected", host: "hu-nandam-hyd" });
        }
      }
    };
    fetchDevCompute();
    const timer = setInterval(fetchDevCompute, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [setDevComputeStatus]);
  const devComputeActive = devComputeStatus?.status === "ssh_connected" || devComputeStatus?.mode === "dev_compute";

  return (
    <div className="grid grid-3">
      <div className="grid">
        <HistorySidebar />
        <SessionHistory />
        <RoundTracker current={currentRound} max={maxRounds} history={roundHistory} />
        <IssueTracker breakdown={issueBreakdown} />
      </div>

      <GlassCard>
        <AgentStatusBar sessionId={sessionId} />
        <NegotiationStatusBar sessionId={sessionId} />
        {!sessionId ? <p>No active session. Go to Input screen first.</p> : null}

        <div className="round-divider">
          ROUND {currentRound} — Patch Quality: {qualityScore.toFixed(0)}%
        </div>

        {patchwiseNotice ? (
          <div className="patchwise-banner">
            ⚠️ {patchwiseNotice}
          </div>
        ) : null}

        <ThreadView messages={messages} sessionId={sessionId} />

        {devComputeActive ? (
          <div style={{ marginTop: 8 }}>
            <DevComputePanel sessionId={sessionId} agent="chanakya" />
            <DevComputePanel sessionId={sessionId} agent="aryabhata" />
          </div>
        ) : null}

        <NegotiationVisualizer sessionId={sessionId} />
        <NegotiationLog sessionId={sessionId} />

        {coverLetterDraft ? (
          <CoverLetterApprovalCard
            draft={coverLetterDraft}
            onApprove={(finalDraft) => {
              setCoverLetterDraft({ ...coverLetterDraft, draft: finalDraft, approved: true });
            }}
            onEdit={(edited) => setCoverLetterDraft({ ...coverLetterDraft, draft: edited })}
            onDismiss={() => setCoverLetterDraft(null)}
          />
        ) : null}

        {patchEvolutionRounds.length > 0 ? (
          <PatchEvolutionTimeline sessionId={sessionId} rounds={patchEvolutionRounds} />
        ) : null}

        {jointVerdict ? <JointLGTMSummary summary={jointVerdict} /> : null}

        {verdict === "LGTM" ? (
          <div className="lgtm-banner">✅ LGTM — CHANAKYA approves the patch!</div>
        ) : null}

        {approvalToken ? (
          <div
            style={{
              marginTop: 10,
              padding: "8px 10px",
              borderRadius: 8,
              border: "1px solid rgba(16,185,129,0.4)",
              background: "rgba(16,185,129,0.12)",
              color: "#6ee7b7",
              fontFamily: "monospace",
              fontSize: 11,
              cursor: "pointer",
            }}
            onClick={() => {
              if (!jointVerdict) setJointVerdict({ token: approvalToken, verdict: "LGTM" });
            }}
          >
            ARYABHATA approval token active: {approvalToken}
          </div>
        ) : null}

        <InterruptPanel
          isPaused={isPaused}
          isAborted={isAborted}
          hint={hint}
          setHint={setHint}
          sendInterrupt={sendInterrupt}
          sendResume={sendResume}
          sendAbort={sendAbort}
          roundInfo={`Round ${currentRound}/${maxRounds}`}
        />

        <div style={{ marginTop: 10 }}>
          <Link className="btn secondary" to="/diff">Go to Diff & Output</Link>
        </div>
      </GlassCard>

      <div className="grid">
        <GlassCard>
          <h4>Patch quality gauge</h4>
          <div
            style={{
              marginTop: 8,
              width: "100%",
              height: 10,
              borderRadius: 999,
              background: "rgba(255,255,255,0.08)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.max(0, Math.min(100, qualityScore))}%`,
                height: "100%",
                background: "linear-gradient(90deg, #ff7f7f, #ffb347, #4fffb0)",
              }}
            />
          </div>
          <p style={{ marginTop: 8 }}>{qualityScore.toFixed(0)} / 100</p>
        </GlassCard>
      </div>
      <FloatingNavButtons />
    </div>
  );
}
