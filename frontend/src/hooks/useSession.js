import axios from "axios";
import useSessionStore from "../store/sessionStore";

const api = axios.create({ baseURL: "/api" });

export default function useSession() {
  const store = useSessionStore();

  const startSession = async () => {
    const payload = {
      kernel_version: store.kernelVersion,
      subsystem: store.subsystem,
      source_path: store.sourcePath,
      llm_model: store.llmModel,
      max_rounds: store.maxRounds,
    };

    const response = await api.post("/session/start", payload);
    store.setField("sessionId", response.data.session_id);
    return response.data;
  };

  const submitPatch = async (sessionId, patchInput) => {
    const response = await api.post("/patch/submit", {
      session_id: sessionId,
      patch_input: patchInput,
    });
    store.setField("patchId", response.data.patch_id);
    store.setField("originalPatch", patchInput);
    store.setField("currentPatch", patchInput);
    return response.data;
  };

  const fetchReport = async (sessionId) => {
    const response = await api.get(`/output/${sessionId}/report`);
    store.setReport(response.data);
    return response.data;
  };

  const fetchPatchOutput = async (sessionId) => {
    const response = await api.get(`/output/${sessionId}/patch`);
    store.setField("currentPatch", response.data.current_patch || "");
    store.setField("verdict", response.data.verdict || "PENDING");
    return response.data;
  };

  const fetchLog = async (sessionId) => {
    const response = await api.get(`/output/${sessionId}/log`);
    return response.data;
  };

  return {
    startSession,
    submitPatch,
    fetchReport,
    fetchPatchOutput,
    fetchLog,
  };
}
