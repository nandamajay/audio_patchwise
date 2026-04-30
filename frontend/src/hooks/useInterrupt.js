import { useCallback, useEffect, useState } from "react";
import useSessionStore from "../store/sessionStore";

export const useInterrupt = (sessionId, sendEvent) => {
  const [isPaused, setIsPaused] = useState(false);
  const [isAborted, setIsAborted] = useState(false);
  const [hint, setHint] = useState("");
  const messages = useSessionStore((state) => state.messages);
  const addSystemMessage = useSessionStore((state) => state.addSystemMessage);

  const sendInterrupt = useCallback((inlineHint = "") => {
    if (!sessionId) return;
    sendEvent?.({ type: "interrupt", hint: inlineHint || hint });
    setIsPaused(true);
  }, [sessionId, sendEvent, hint]);

  const sendResume = useCallback(() => {
    if (!sessionId) return;
    sendEvent?.({ type: "resume" });
    setIsPaused(false);
    setHint("");
  }, [sessionId, sendEvent]);

  const sendAbort = useCallback(() => {
    if (!sessionId) return;
    sendEvent?.({ type: "abort" });
    setIsPaused(false);
    setIsAborted(true);
  }, [sessionId, sendEvent]);

  useEffect(() => {
    const latest = messages[messages.length - 1];
    if (!latest) return;

    if (latest.type === "session_paused") setIsPaused(true);
    if (latest.type === "session_resumed") setIsPaused(false);
    if (latest.type === "session_aborted") {
      setIsPaused(false);
      setIsAborted(true);
    }
    if (latest.type === "interrupt_acknowledged") {
      addSystemMessage(latest.message || latest.content || "Interrupt acknowledged.");
    }
  }, [messages, addSystemMessage]);

  return { isPaused, isAborted, hint, setHint, sendInterrupt, sendResume, sendAbort };
};

export default useInterrupt;
