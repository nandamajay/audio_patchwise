import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";

import AgentBubble from "../components/agents/AgentBubble";
import InterruptPanel from "../components/ChatThread/InterruptPanel";
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
    issueBreakdown,
    roundHistory,
    fetchSessions,
  } = useSessionStore();

  const { sendEvent } = useAgentStream(sessionId);
  const { isPaused, isAborted, hint, setHint, sendInterrupt, sendResume, sendAbort } = useInterrupt(sessionId, sendEvent);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const grouped = useMemo(() => {
    const map = new Map();
    messages.forEach((message) => {
      const round = message.round || 1;
      if (!map.has(round)) map.set(round, []);
      map.get(round).push(message);
    });
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [messages]);

  return (
    <div className="grid grid-3">
      <div className="grid">
        <SessionHistory />
        <RoundTracker current={currentRound} max={maxRounds} history={roundHistory} />
        <IssueTracker breakdown={issueBreakdown} />
      </div>

      <GlassCard>
        {!sessionId ? <p>No active session. Go to Input screen first.</p> : null}

        {grouped.map(([round, items]) => (
          <div key={`round-${round}`}>
            <div className="round-divider">
              ROUND {round} — Patch Quality: {qualityScore.toFixed(0)}%
            </div>
            {items.map((item) => (
              <AgentBubble key={item.id} message={item} />
            ))}
          </div>
        ))}

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
