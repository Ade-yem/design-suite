import { MessageSquare } from "lucide-react";
import { StageTracker, type Stage } from "./StageTracker";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

interface WorkspaceHeaderProps {
  currentStage: Stage;
}

export function WorkspaceHeader({ currentStage }: WorkspaceHeaderProps) {
  const { chatOpen, chatUnread, toggleChat } = useUIStore();

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-card shrink-0">
      <div className="flex-1" />

      <StageTracker currentStage={currentStage} />

      <div className="flex-1 flex justify-end">
        <button
          onClick={toggleChat}
          className={cn(
            "relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors",
            chatOpen
              ? "text-primary bg-primary/10"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
          aria-label={chatOpen ? "Hide chat" : "Show chat"}
          title={chatOpen ? "Hide chat (⌘\\)" : "Show chat (⌘\\)"}
        >
          <MessageSquare className="h-4 w-4" />
          {!chatOpen && chatUnread > 0 && (
            <span className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-primary text-primary-foreground text-[9px] font-semibold flex items-center justify-center">
              {chatUnread > 9 ? "9+" : chatUnread}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
