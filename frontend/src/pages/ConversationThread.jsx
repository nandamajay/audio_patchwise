import { useEffect } from "react";
import { Link } from "react-router-dom";

import InterruptPanel from "../components/ChatThread/InterruptPanel";
import ThreadView from "../components/AgentThread/ConversationThread";
import IssueTracker from "../components/controls/IssueTracker";
import RoundTracker from "../components/controls/RoundTracker";
import SessionHistory from "../components/SessionHistory/SessionHistory";
import GlassCard from "../components/layout/GlassCard";
import useAgentStream from "../hooks/useAgentStream";
import useInterrupt from "../hooks/useInterrupt";
import useSessionStore from "../store/sessionStore";

export default function ConversationThread() {
  const {
    sessionId,
    currentRound,
    maxRounds,
    messages,
    qualityScore,
    verdict,
    patchwiseNotice,
    issueBreakdown,
    roundHistory,
    fetchSessions,
  } = useSessionStore();

  const { sendEvent } = useAgentStream(sessionId);
  const { isPaused, isAborted, hint, setHint, sendInterrupt, sendResume, sendAbort } = useInterrupt(sessionId, sendEvent);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  return (
    <div className="grid grid-3">
      <div className="grid">
        <SessionHistory />
        <RoundTracker current={currentRound} max={maxRounds} history={roundHistory} />
        <IssueTracker breakdown={issueBreakdown} />
      </div>

      <GlassCard>
        {!sessionId ? <p>No active session. Go to Input screen first.</p> : null}

        <div className="round-divider">
          ROUND {currentRound} — Patch Quality: {qualityScore.toFixed(0)}%
        </div>

        {patchwiseNotice ? (
          <div className="patchwise-banner">
            ⚠️ {patchwiseNotice}
          </div>
        ) : null}

        <ThreadView messages={messages} />

        {verdict === "LGTM" ? (
          <div className="lgtm-banner">✅ LGTM — CHANAKYA approves the patch!</div>
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
    </div>
  );
}
