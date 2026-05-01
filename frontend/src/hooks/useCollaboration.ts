import { useCallback, useEffect, useState } from "react";
import { socket } from "../socket";

export interface Participant {
  username: string;
  role: "owner" | "co_reviewer" | "observer";
  joined_at: string;
}

export interface HumanComment {
  id: string;
  username: string;
  role: string;
  comment: string;
  message_ref: string;
  timestamp: string;
}

export function useCollaboration(sessionId: string) {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [comments, setComments] = useState<HumanComment[]>([]);
  const [raisedHands, setRaisedHands] = useState<string[]>([]);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [pinnedMessages, setPinnedMessages] = useState<string[]>([]);

  useEffect(() => {
    socket.on("participant_joined", (data) => {
      setParticipants((prev) => [
        ...prev,
        {
          username: data.username,
          role: data.role,
          joined_at: new Date().toISOString(),
        },
      ]);
    });

    socket.on("presence_update", (data) => {
      setParticipants(data.active_participants || []);
    });

    socket.on("human_comment", (comment: HumanComment) => {
      setComments((prev) => [...prev, comment]);
    });

    socket.on("hand_raised", (data) => {
      setRaisedHands((prev) => [...prev, data.message_ref]);
    });

    socket.on("message_pinned", (data) => {
      setPinnedMessages((prev) => [...prev, data.message_ref]);
    });

    return () => {
      socket.off("participant_joined");
      socket.off("presence_update");
      socket.off("human_comment");
      socket.off("hand_raised");
      socket.off("message_pinned");
    };
  }, [sessionId]);

  const createShareLink = useCallback(
    async (role: string = "co_reviewer", expiryHours: number = 24) => {
      const res = await fetch("/api/collab/share", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          owner_id: "current_user",
          role,
          expiry_hours: expiryHours,
        }),
      });
      const data = await res.json();
      setShareLink(data.share_link);
      return data.share_link;
    },
    [sessionId],
  );

  const addComment = useCallback(
    async (messageRef: string, comment: string) => {
      await fetch("/api/collab/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: "current_user",
          username: "You",
          message_ref: messageRef,
          comment,
          role: "co_reviewer",
        }),
      });
    },
    [sessionId],
  );

  const raiseHand = useCallback(
    async (messageRef: string) => {
      await fetch("/api/collab/raise-hand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: "current_user",
          username: "You",
          message_ref: messageRef,
        }),
      });
    },
    [sessionId],
  );

  return {
    participants,
    comments,
    raisedHands,
    pinnedMessages,
    shareLink,
    createShareLink,
    addComment,
    raiseHand,
  };
}
