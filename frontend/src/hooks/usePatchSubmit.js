import useSession from "./useSession";
import useSessionStore from "../store/sessionStore";

export default function usePatchSubmit() {
  const { startSession, submitPatch } = useSession();
  const store = useSessionStore();

  const submit = async () => {
    let sessionId = store.sessionId;
    if (!sessionId) {
      const session = await startSession();
      sessionId = session.session_id;
    }

    await submitPatch(sessionId, store.patchInput || "");
    return sessionId;
  };

  return { submit };
}
