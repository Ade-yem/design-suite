import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface UIState {
  sidebarExpanded: boolean;
  chatOpen: boolean;
  chatUnread: number;
}

interface UIActions {
  toggleSidebar: () => void;
  setSidebarExpanded: (v: boolean) => void;
  toggleChat: () => void;
  setChatOpen: (v: boolean) => void;
  incrementUnread: () => void;
  clearUnread: () => void;
}

export type UIStore = UIState & UIActions;

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarExpanded: true,
      chatOpen: true,
      chatUnread: 0,

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
    }),
    {
      name: "structai-ui-state",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sidebarExpanded: state.sidebarExpanded,
        chatOpen: state.chatOpen,
      }),
    }
  )
);
