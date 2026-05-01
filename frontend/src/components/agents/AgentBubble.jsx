import AryabhataAvatar from "./AryabhataAvatar";
import ChanakyaAvatar from "./ChanakyaAvatar";
import ThinkingCard from "./ThinkingCard";
import JustificationCard from "./JustificationCard";
import SimilarPatchCard from "../patch/SimilarPatchCard";
import StatusBadge from "../layout/StatusBadge";
import AryabhataMessage from "../AgentThread/AryabhataMessage";
import AryabhataFixMessage from "../AryabhataFixMessage";
import FeedbackButtons from "../FeedbackButtons";
import ReviewIssueCard from "../ReviewIssueCard";
import ThoughtChainTree from "../ThoughtChainTree";

const badgeTone = {
  CRITICAL: "danger",
  WARNING: "warning",
  INFO: "default",
};

export default function AgentBubble({ message, sessionId }) {
  const isSystem = message.agent === "system";
  const isChanakya = message.agent === "chanakya";
  const sideClass = isSystem ? "left" : isChanakya ? "left" : "right";
  const bubbleClass = isSystem ? "aryabhata" : isChanakya ? "chanakya" : "aryabhata";

  return (
    <div className={`agent-bubble ${sideClass}`}>
      {isSystem ? null : isChanakya ? <ChanakyaAvatar size={48} /> : <AryabhataAvatar size={48} />}
      <div className={`bubble-content ${bubbleClass}`}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <strong>{isSystem ? "🔔 System" : isChanakya ? "CHANAKYA (Reviewer)" : "ARYABHATA (Developer)"}</strong>
          {message.metadata?.severity ? (
            <StatusBadge label={message.metadata.severity} tone={badgeTone[message.metadata.severity] || "default"} />
          ) : null}
        </div>

        <p style={{ whiteSpace: "pre-wrap" }}>
          {message.content}
          {message.streaming ? <span className="streaming-cursor" /> : null}
        </p>

        {message.type === "FIX_APPLIED" ? (
          <AryabhataMessage message={message} />
        ) : null}

        {message.type === "fix_complete" ? (
          <AryabhataFixMessage message={message} />
        ) : null}

        {message.type === "thinking" ? (
          <ThinkingCard
            title={isChanakya ? "🧠 Thinking..." : "⚙️ Computing fix..."}
            content={message.content}
          />
        ) : null}

        {message.type === "justification" ? <JustificationCard card={message.metadata} /> : null}

        {message.type === "finding" && message.metadata?.issue_type ? (
          <ReviewIssueCard
            issue={
              message.metadata.issue || {
                issue_id: message.metadata.issue_id || message.id,
                category: message.metadata.issue_type,
                severity: message.metadata.severity || "WARNING",
                line_number: message.metadata.line_number || 1,
                file_path: "unknown",
                hunk_context: "",
                error_message: message.content,
                problematic_code: message.metadata.problematic_code || "",
                suggested_fix: message.metadata.suggested_fix || "",
                explanation: message.metadata.explanation || message.content,
                reference: message.metadata.reference || null,
                is_recurring: Boolean(message.metadata.recurring),
                previous_round: message.metadata.first_seen || null,
              }
            }
          />
        ) : null}

        {message.type === "similar_patch" ? <SimilarPatchCard refData={message.metadata} /> : null}

        {!isSystem ? (
          <FeedbackButtons
            sessionId={sessionId}
            roundNum={message.round || message.round_num || 1}
            agent={message.agent}
            messageId={message.id}
            messageContent={message.content}
            issueType={message.metadata?.issue_type || message.issue_type}
          />
        ) : null}

        {message.thought_chain ? (
          <ThoughtChainTree
            thoughtChain={message.thought_chain}
            agentName={message.agent === "chanakya" ? "CHANAKYA (Reviewer)" : "ARYABHATA (Developer)"}
            agentColor={message.agent === "chanakya" ? "var(--accent-blue)" : "var(--accent-purple)"}
          />
        ) : null}
      </div>
    </div>
  );
}
