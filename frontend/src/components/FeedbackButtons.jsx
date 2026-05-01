import { useState } from "react";
import { MessageSquare, ThumbsDown, ThumbsUp } from "lucide-react";

export default function FeedbackButtons({
  sessionId,
  roundNum,
  agent,
  messageId,
  messageContent,
  issueType,
}) {
  const [voted, setVoted] = useState(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submitVote = async (vote, optionalComment = "") => {
    setSubmitting(true);
    await fetch("/api/feedback/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        round_num: roundNum,
        agent,
        message_id: messageId,
        message_content: messageContent,
        vote: vote === "up" ? 1 : -1,
        comment: optionalComment || undefined,
        issue_type: issueType,
        subsystem: "audio",
      }),
    });

    setVoted(vote);
    setShowComment(false);
    setSubmitting(false);
  };

  if (voted) {
    return (
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "4px 10px",
          borderRadius: "12px",
          background: voted === "up" ? "rgba(0,214,143,0.1)" : "rgba(255,61,113,0.1)",
          color: voted === "up" ? "#00d68f" : "#ff3d71",
          fontSize: "11px",
          fontWeight: 600,
          marginTop: "6px",
        }}
      >
        {voted === "up" ? "Thanks for the feedback" : "Noted - will improve"}
      </div>
    );
  }

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", marginTop: "6px", position: "relative" }}>
      <button
        type="button"
        onClick={() => submitVote("up")}
        disabled={submitting}
        title="This was helpful"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          padding: "4px 10px",
          borderRadius: "12px",
          border: "1px solid rgba(0,214,143,0.3)",
          background: "rgba(0,214,143,0.08)",
          color: "#00d68f",
          cursor: "pointer",
          fontSize: "11px",
        }}
      >
        <ThumbsUp size={12} /> Helpful
      </button>

      <button
        type="button"
        onClick={() => setShowComment(true)}
        disabled={submitting}
        title="This was not helpful"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          padding: "4px 10px",
          borderRadius: "12px",
          border: "1px solid rgba(255,61,113,0.3)",
          background: "rgba(255,61,113,0.08)",
          color: "#ff3d71",
          cursor: "pointer",
          fontSize: "11px",
        }}
      >
        <ThumbsDown size={12} /> Not Helpful
      </button>

      {showComment ? (
        <div
          style={{
            position: "absolute",
            top: "28px",
            left: 0,
            background: "var(--bg-card)",
            border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: "12px",
            padding: "14px",
            width: "280px",
            zIndex: 100,
            backdropFilter: "blur(12px)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "10px" }}>
            <MessageSquare size={14} color="#ff3d71" />
            <span style={{ color: "#fff", fontSize: "13px", fontWeight: 600 }}>What was wrong? (optional)</span>
          </div>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="e.g. This suggestion was already applied..."
            style={{
              width: "100%",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "8px",
              padding: "8px",
              color: "#fff",
              fontSize: "12px",
              resize: "none",
              height: "60px",
              outline: "none",
            }}
          />
          <div style={{ display: "flex", gap: "8px", marginTop: "10px" }}>
            <button
              type="button"
              onClick={() => submitVote("down", comment)}
              style={{
                flex: 1,
                padding: "8px",
                borderRadius: "8px",
                border: "none",
                background: "linear-gradient(135deg, #ff3d71, #cc2255)",
                color: "#fff",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              Submit
            </button>
            <button
              type="button"
              onClick={() => setShowComment(false)}
              style={{
                padding: "8px 14px",
                borderRadius: "8px",
                border: "1px solid rgba(255,255,255,0.1)",
                background: "transparent",
                color: "#8f9bb3",
                cursor: "pointer",
                fontSize: "12px",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
