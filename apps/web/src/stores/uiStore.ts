import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

/** Identity of a safety gate awaiting the engineer's approval. */
export interface PendingGate {
  gate: string;
  label: string;
}

interface UIState {
  sidebarExpanded: boolean;
  chatOpen: boolean;
  chatUnread: number;
  /**
   * The safety gate currently awaiting the engineer's approval, or null.
   * This is the single source of truth shared by the pipeline rail (which owns
   * the approve action) and the chat (which points the engineer to the rail).
   */
  pendingGate: PendingGate | null;
  pipelineRailExpanded: boolean;
  membersPanelExpanded: boolean;
}

interface UIActions {
  toggleSidebar: () => void;
  setSidebarExpanded: (v: boolean) => void;
  toggleChat: () => void;
  setChatOpen: (v: boolean) => void;
  incrementUnread: () => void;
  clearUnread: () => void;
  setPendingGate: (g: PendingGate | null) => void;
  setPipelineRailExpanded: (v: boolean) => void;
  setMembersPanelExpanded: (v: boolean) => void;
}

export type UIStore = UIState & UIActions;

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarExpanded: true,
      chatOpen: true,
      chatUnread: 0,
      pendingGate: null,
      pipelineRailExpanded: true,
      membersPanelExpanded: true,

      toggleSidebar: () => set((s) => ({ sidebarExpanded: !s.sidebarExpanded })),
      setSidebarExpanded: (v) => set({ sidebarExpanded: v }),

      toggleChat: () =>
        set((s) => ({
          chatOpen: !s.chatOpen,
          chatUnread: !s.chatOpen ? 0 : s.chatUnread,
        })),
      setChatOpen: (v) =>
        set((s) => ({
          chatOpen: v,
          chatUnread: v ? 0 : s.chatUnread,
        })),

      incrementUnread: () => set((s) => ({ chatUnread: s.chatUnread + 1 })),
      clearUnread: () => set({ chatUnread: 0 }),
      setPendingGate: (g) => set({ pendingGate: g }),
      setPipelineRailExpanded: (v) => set({ pipelineRailExpanded: v }),
      setMembersPanelExpanded: (v) => set({ membersPanelExpanded: v }),
    }),
    {
      name: "structai-ui-state",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sidebarExpanded: state.sidebarExpanded,
        chatOpen: state.chatOpen,
        pipelineRailExpanded: state.pipelineRailExpanded,
        membersPanelExpanded: state.membersPanelExpanded,
      }),
    }
  )
);
