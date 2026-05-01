import { useEffect, useMemo, useRef, useState } from "react";

import AgentBubble from "../agents/AgentBubble";

export default function ConversationThread({ messages, sessionId }) {
  const topRef = useRef(null);
  const bottomRef = useRef(null);
  const [showNav, setShowNav] = useState(false);

  useEffect(() => {
    setShowNav((messages || []).length > 3);
  }, [messages]);

  const scrollToTop = () => topRef.current?.scrollIntoView({ behavior: "smooth" });
  const scrollToBottom = () => bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  const grouped = useMemo(() => {
    const map = new Map();
    (messages || []).forEach((message) => {
      const round = message.round || 1;
      if (!map.has(round)) map.set(round, []);
      map.get(round).push(message);
    });
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [messages]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={topRef} />
      {grouped.map(([round, roundMessages]) => (
        <div key={`round-${round}`}>
          <div className="round-divider">ROUND {round}</div>
          {roundMessages.map((message) => (
            <AgentBubble key={message.id} message={message} sessionId={sessionId} />
          ))}
        </div>
      ))}
      <div ref={bottomRef} />

      {showNav ? (
        <div className="thread-nav-buttons">
          <button className="nav-btn glass" onClick={scrollToTop} title="Go to top" type="button">
            ⬆ Top
          </button>
          <button className="nav-btn glass" onClick={scrollToBottom} title="Go to bottom" type="button">
            ⬇ Latest
          </button>
        </div>
      ) : null}
    </div>
  );
}
