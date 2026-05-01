import { useEffect, useMemo, useRef, useState } from "react";

import AgentBubble from "../agents/AgentBubble";
import { ImpactMap, TimeoutSlider } from "../ConversationThread";

export default function ConversationThread({
  messages,
  impactRadius = null,
  touchedLines = [],
  challengeTimeout = 60,
  onTimeoutChange = () => undefined,
  getNegotiationThread = () => [],
}) {
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
      {impactRadius ? (
        <ImpactMap impactRadius={impactRadius} touchedLines={touchedLines} />
      ) : null}
      <div ref={topRef} />
      {grouped.map(([round, roundMessages]) => (
        <div key={`round-${round}`}>
          <div className="round-divider">ROUND {round}</div>
          {roundMessages.map((message) => (
            <AgentBubble
              key={message.id}
              message={message}
              getNegotiationThread={getNegotiationThread}
            />
          ))}
        </div>
      ))}
      <div ref={bottomRef} />

      <div style={{ marginTop: 8, marginBottom: 10 }}>
        <TimeoutSlider value={challengeTimeout} onChange={onTimeoutChange} />
      </div>

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
