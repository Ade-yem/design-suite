import { useEffect } from "react";
import { useUIStore } from "@/stores/uiStore";

interface KeyboardShortcutsOptions {
  onNewProject?: () => void;
  onFocusSearch?: () => void;
}

export function useKeyboardShortcuts({
  onNewProject,
  onFocusSearch,
}: KeyboardShortcutsOptions = {}) {
  const { toggleSidebar, toggleChat } = useUIStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      switch (e.key) {
        case "b":
          e.preventDefault();
          toggleSidebar();
          break;
        case "\\":
          e.preventDefault();
          toggleChat();
          break;
        case "k":
          e.preventDefault();
          onFocusSearch?.();
          break;
        case "n":
          e.preventDefault();
          onNewProject?.();
          break;
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleSidebar, toggleChat, onNewProject, onFocusSearch]);
}
