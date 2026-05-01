import axios from "axios";
import { create } from "zustand";

const api = axios.create({ baseURL: "/api" });
const PROVIDERS = new Set(["qgenie", "openai", "anthropic", "mock", "qualcomm"]);

function toSelection(config) {
  const providerRaw = String(config?.llm_provider || "").toLowerCase();
  const provider = providerRaw === "qualcomm" ? "qgenie" : providerRaw;
  const modelRaw = String(config?.llm_model || "").trim();

  if (provider.includes("/")) return provider;
  if (provider.includes(":")) return provider.replace(":", "/");
  if (PROVIDERS.has(provider)) return `${provider}/${modelRaw || "gpt-4o"}`;
  if (provider) return `qgenie/${provider}`;
  return "qgenie/gpt-4o";
}

const useSessionStore = create((set, get) => ({
  sessionId: "",
  currentSessionId: null,
  patchId: "",
  patchInput: "",
  originalPatch: "",
  currentPatch: "",
  kernelVersion: "6.9",
  subsystem: "alsa-asoc",
  sourcePath: "sound/soc/",
  llmModel: "qgenie/gpt-4o",
  maxRounds: 5,
  currentRound: 1,
  qualityScore: 0,
  verdict: "PENDING",
  connected: false,
  issueBreakdown: {},
  roundHistory: [],
  messages: [],
  report: null,
  sessions: [],
  loadingSessions: false,

  setField: (field, value) => set(() => ({ [field]: value })),
  setSession: (payload) => set(() => ({ ...payload })),
  setCurrentSession: (sessionId) => set(() => ({ currentSessionId: sessionId, sessionId })),

  addSystemMessage: (content) =>
    set((state) => {
      const id = `system-${state.messages.length}`;
      return {
        messages: [
          ...state.messages,
          {
            id,
            agent: "system",
            type: "interrupt_acknowledged",
            round: state.currentRound,
            content,
            metadata: {},
          },
        ],
      };
    }),

  addMessage: (message) =>
    set((state) => {
      const id = `${message.agent}-${message.type}-${message.round}-${state.messages.length}`;
      return { messages: [...state.messages, { id, ...message }] };
    }),

  updateStreamingMessage: (incoming) =>
    set((state) => {
      const normalized = {
        ...incoming,
        content: incoming.content || incoming.message || "",
      };

      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      const sameStream =
        last &&
        last.agent === normalized.agent &&
        last.type === normalized.type &&
        last.round === normalized.round;

      if (sameStream && ["thinking", "justification"].includes(normalized.type)) {
        last.content = `${last.content || ""}${normalized.content || ""}`;
        last.streaming = true;
      } else {
        const id = `${normalized.agent}-${normalized.type}-${normalized.round}-${messages.length}`;
        messages.push({
          id,
          ...normalized,
          streaming: ["thinking", "justification"].includes(normalized.type),
        });
      }

      const issueBreakdown = { ...state.issueBreakdown };
      if (normalized.type === "finding") {
        const key = normalized.metadata?.issue_type || "UNKNOWN";
        issueBreakdown[key] = (issueBreakdown[key] || 0) + 1;
      }

      const qualityScore = normalized.metadata?.quality_score ?? state.qualityScore;
      const verdict =
        normalized.type === "lgtm"
          ? "LGTM"
          : normalized.metadata?.verdict || state.verdict;

      const roundHistory = [...state.roundHistory];
      if (["verdict", "lgtm"].includes(normalized.type)) {
        roundHistory.push({
          round: normalized.round,
          summary: normalized.type === "lgtm" ? "LGTM" : normalized.content,
        });
      }

      return {
        messages,
        issueBreakdown,
        qualityScore,
        verdict,
        currentRound: normalized.round || state.currentRound,
        roundHistory,
      };
    }),

  markConnected: (connected) => set(() => ({ connected })),
  setReport: (report) => set(() => ({ report })),

  fetchSessions: async () => {
    set(() => ({ loadingSessions: true }));
    try {
      const response = await api.get("/sessions/");
      set(() => ({ sessions: response.data.sessions || [] }));
    } catch {
      set(() => ({ sessions: [] }));
    } finally {
      set(() => ({ loadingSessions: false }));
    }
  },

  loadSession: async (sessionId) => {
    const response = await api.get(`/sessions/${sessionId}`);
    const snapshot = response.data;

    set(() => ({
      currentSessionId: snapshot.session_id,
      sessionId: snapshot.session_id,
      patchInput: snapshot.patch_input?.raw_text || "",
      originalPatch: snapshot.patch_input?.raw_text || "",
      currentPatch: snapshot.final_patch || snapshot.patch_input?.raw_text || "",
      kernelVersion: snapshot.context?.kernel_version || "",
      subsystem: snapshot.context?.subsystem || "alsa-asoc",
      sourcePath: snapshot.context?.source_path || "",
      llmModel: toSelection(snapshot.config),
      maxRounds: snapshot.max_rounds || 5,
      currentRound: snapshot.current_round || 1,
      messages: (snapshot.conversation || []).map((message, index) => ({
        id: `loaded-${index}`,
        ...message,
      })),
      verdict: snapshot.verdict || "PENDING",
      report: snapshot.review_report || null,
    }));
  },

  resumeSession: async (sessionId) => {
    await api.post(`/sessions/${sessionId}/resume`);
    await get().loadSession(sessionId);
  },

  deleteSession: async (sessionId) => {
    await api.delete(`/sessions/${sessionId}`);
    await get().fetchSessions();
  },

  resetConversation: () =>
    set(() => ({
      patchId: "",
      currentSessionId: null,
      sessionId: "",
      originalPatch: "",
      currentPatch: "",
      currentRound: 1,
      qualityScore: 0,
      verdict: "PENDING",
      issueBreakdown: {},
      roundHistory: [],
      messages: [],
      report: null,
    })),
}));

export default useSessionStore;
