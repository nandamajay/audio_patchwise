import AryabhataAvatar from "./AryabhataAvatar";
import ChanakyaAvatar from "./ChanakyaAvatar";
import ThinkingCard from "./ThinkingCard";
import JustificationCard from "./JustificationCard";
import SimilarPatchCard from "../patch/SimilarPatchCard";
import StatusBadge from "../layout/StatusBadge";
import AryabhataMessage from "../AgentThread/AryabhataMessage";

const badgeTone = {
  CRITICAL: "danger",
  WARNING: "warning",
  INFO: "default",
};

export default function AgentBubble({ message }) {
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

        {message.type === "thinking" ? (
          <ThinkingCard
            title={isChanakya ? "🧠 Thinking..." : "⚙️ Computing fix..."}
            content={message.content}
          />
        ) : null}

        {message.type === "justification" ? <JustificationCard card={message.metadata} /> : null}

        {message.type === "finding" && message.metadata?.issue_type ? (
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <span className={`badge ${String(message.metadata.issue_type).toLowerCase()}`}>{message.metadata.issue_type}</span>
            <span className="small">line {message.metadata.line_number}</span>
            {message.metadata?.recurring ? (
              <span className="badge recurring">
                ⚠️ Recurring — Round {message.metadata.first_seen}
              </span>
            ) : null}
          </div>
        ) : null}

        {message.type === "similar_patch" ? <SimilarPatchCard refData={message.metadata} /> : null}
      </div>
    </div>
  );
}
