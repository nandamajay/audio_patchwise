import axios from "axios";
import { useCallback, useMemo } from "react";
import useSessionStore from "../store/sessionStore";

const api = axios.create({ baseURL: "/api" });

export default function useSession() {
  const kernelVersion = useSessionStore((state) => state.kernelVersion);
  const subsystem = useSessionStore((state) => state.subsystem);
  const sourcePath = useSessionStore((state) => state.sourcePath);
  const llmModel = useSessionStore((state) => state.llmModel);
  const maxRounds = useSessionStore((state) => state.maxRounds);
  const setField = useSessionStore((state) => state.setField);
  const setReport = useSessionStore((state) => state.setReport);

  const startSession = useCallback(async () => {
    const llmSelection = String(llmModel || "");
    let llmProviderRaw = "qgenie";
    let llmModelRaw = "gpt-4o";
    if (llmSelection.includes("/")) {
      [llmProviderRaw, llmModelRaw] = llmSelection.split("/", 2);
    } else if (llmSelection.includes(":")) {
      [llmProviderRaw, llmModelRaw] = llmSelection.split(":", 2);
    } else if (llmSelection.endsWith("-qgenie")) {
      llmProviderRaw = "qgenie";
      llmModelRaw = llmSelection.replace(/-qgenie$/, "");
    } else if (llmSelection.endsWith("-openai")) {
      llmProviderRaw = "openai";
      llmModelRaw = llmSelection.replace(/-openai$/, "");
    } else if (llmSelection.endsWith("-anthropic")) {
      llmProviderRaw = "anthropic";
      llmModelRaw = llmSelection.replace(/-anthropic$/, "");
    } else if (llmSelection) {
      llmModelRaw = llmSelection;
    }
    const llmProvider = llmProviderRaw || "qgenie";
    const resolvedModel = llmModelRaw || "gpt-4o";

    const payload = {
      kernel_version: kernelVersion,
      subsystem,
      source_path: sourcePath,
      llm_provider: llmProvider,
      llm_model: resolvedModel,
      max_rounds: maxRounds,
    };

    const response = await api.post("/session/start", payload);
    setField("sessionId", response.data.session_id);
    return response.data;
  }, [kernelVersion, subsystem, sourcePath, llmModel, maxRounds, setField]);

  const submitPatch = useCallback(async (sessionId, patchInput) => {
    const response = await api.post("/patch/submit", {
      session_id: sessionId,
      patch_input: patchInput,
    });
    setField("patchId", response.data.patch_id);
    setField("originalPatch", patchInput);
    setField("currentPatch", patchInput);
    return response.data;
  }, [setField]);

  const fetchReport = useCallback(async (sessionId) => {
    try {
      const response = await api.get(`/output/${sessionId}/report`);
      setReport(response.data);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setReport(null);
        setField("sessionId", "");
      }
      throw error;
    }
  }, [setReport, setField]);

  const fetchPatchOutput = useCallback(async (sessionId) => {
    try {
      const response = await api.get(`/output/${sessionId}/patch`);
      setField("currentPatch", response.data.current_patch || "");
      setField("verdict", response.data.verdict || "PENDING");
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setField("currentPatch", "");
        setField("verdict", "PENDING");
        setField("sessionId", "");
      }
      throw error;
    }
  }, [setField]);

  const fetchLog = useCallback(async (sessionId) => {
    const response = await api.get(`/output/${sessionId}/log`);
    return response.data;
  }, []);

  return useMemo(() => ({
    startSession,
    submitPatch,
    fetchReport,
    fetchPatchOutput,
    fetchLog,
  }), [startSession, submitPatch, fetchReport, fetchPatchOutput, fetchLog]);
}
