import { create } from "zustand";
import { persist } from "zustand/middleware";

const API = import.meta.env.VITE_API_URL || "";
let replayTimer = null;

const clearReplayTimer = () => {
  if (replayTimer) {
    clearTimeout(replayTimer);
    replayTimer = null;
  }
};

const useHistoryStore = create(
  persist(
    (set, get) => ({
      sessions: [],
      selectedSession: null,
      replayData: null,
      replayIndex: 0,
      isReplaying: false,
      replaySpeed: 1,
      globalStats: null,
      analytics: null,
      filters: { subsystem: "", verdict: "", date_from: "", date_to: "" },
      search: "",
      activeTab: "conversation",

      fetchSessions: async () => {
        const { filters, search } = get();
        const params = new URLSearchParams();
        if (search) params.set("search", search);
        if (filters.subsystem) params.set("subsystem", filters.subsystem);
        if (filters.verdict) params.set("verdict", filters.verdict);
        if (filters.date_from) params.set("date_from", filters.date_from);
        if (filters.date_to) params.set("date_to", filters.date_to);

        const res = await fetch(`${API}/api/history/sessions?${params.toString()}`);
        const sessions = await res.json();
        set({ sessions: Array.isArray(sessions) ? sessions : [] });
      },

      selectSession: async (sessionId) => {
        const [sessionRes, replayRes, analyticsRes] = await Promise.all([
          fetch(`${API}/api/history/sessions/${sessionId}`),
          fetch(`${API}/api/history/sessions/${sessionId}/replay`),
          fetch(`${API}/api/history/sessions/${sessionId}/analytics`),
        ]);

        const selectedSession = await sessionRes.json();
        const replayData = await replayRes.json();
        const analytics = await analyticsRes.json();
        clearReplayTimer();
        set({
          selectedSession,
          replayData,
          analytics,
          replayIndex: 0,
          isReplaying: false,
          activeTab: "conversation",
        });
      },

      fetchGlobalStats: async () => {
        const res = await fetch(`${API}/api/history/stats`);
        const globalStats = await res.json();
        set({ globalStats });
      },

      startReplay: () => {
        const runTick = () => {
          const { replayData, replayIndex, isReplaying, replaySpeed } = get();
          const messageCount = replayData?.messages?.length || 0;
          if (!isReplaying || messageCount === 0) {
            return;
          }
          if (replayIndex >= messageCount) {
            clearReplayTimer();
            set({ isReplaying: false });
            return;
          }
          set({ replayIndex: replayIndex + 1 });
          replayTimer = setTimeout(runTick, 800 / (replaySpeed || 1));
        };

        clearReplayTimer();
        set({ isReplaying: true });
        replayTimer = setTimeout(runTick, 800 / (get().replaySpeed || 1));
      },

      pauseReplay: () => {
        clearReplayTimer();
        set({ isReplaying: false });
      },

      rewindReplay: () => {
        clearReplayTimer();
        set({ replayIndex: 0, isReplaying: false });
      },

      setReplaySpeed: (speed) => set({ replaySpeed: speed }),
      setReplayIndex: (index) => set({ replayIndex: index }),
      setActiveTab: (tab) => set({ activeTab: tab }),
      setSearch: (search) => set({ search }),
      setFilters: (nextFilters) => set({ filters: { ...get().filters, ...nextFilters } }),

      exportSession: async (sessionId, type) => {
        const res = await fetch(`${API}/api/history/sessions/${sessionId}/export/${type}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        const disposition = res.headers.get("content-disposition") || "";
        const filename = disposition.split("filename=")[1] || `patchwise-export.${type}`;
        anchor.download = filename.replaceAll('"', "");
        anchor.click();
        URL.revokeObjectURL(url);
      },

      deleteSession: async (sessionId) => {
        await fetch(`${API}/api/history/sessions/${sessionId}`, { method: "DELETE" });
        const sessions = get().sessions.filter((item) => item.id !== sessionId);
        set({
          sessions,
          selectedSession:
            get().selectedSession?.id === sessionId ? null : get().selectedSession,
        });
      },
    }),
    { name: "patchwise-history" },
  ),
);

export default useHistoryStore;
