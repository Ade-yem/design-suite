import { MessageSquare } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

export function WorkspaceHeader() {
  const { chatOpen, chatUnread, toggleChat } = useUIStore();

  return (
    <header className="h-12 flex items-center justify-end px-4 border-b border-border bg-card shrink-0">
      <button
        onClick={toggleChat}
        className={cn(
          "relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors",
          chatOpen
            ? "text-primary bg-primary/10"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
        aria-label={chatOpen ? "Hide chat" : "Show chat"}
        title={chatOpen ? "Hide chat (⌘\\)" : "Show chat (⌘\\)"}
      >
        <MessageSquare className="h-4 w-4" />
        {!chatOpen && chatUnread > 0 && (
          <span className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full text-[9px] font-semibold flex items-center justify-center bg-primary text-primary-foreground">
            {chatUnread > 9 ? "9+" : chatUnread}
          </span>
        )}
      </button>
    </header>
  );
}
