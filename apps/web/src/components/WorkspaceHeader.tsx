import { MessageSquare } from "lucide-react";
import { StageTracker, type Stage } from "./StageTracker";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

interface WorkspaceHeaderProps {
  currentStage: Stage;
}

export function WorkspaceHeader({ currentStage }: WorkspaceHeaderProps) {
  const { chatOpen, chatUnread, gatePending, toggleChat } = useUIStore();

  // Draw attention to the chat toggle when a safety gate is waiting on approval
  // and the panel that hosts it is closed.
  const gateNeedsAttention = gatePending && !chatOpen;

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-card shrink-0">
      <div className="flex-1" />

      <StageTracker currentStage={currentStage} />

      <div className="flex-1 flex justify-end">
        <button
          onClick={toggleChat}
          className={cn(
            "relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors",
            gateNeedsAttention
              ? "text-warning bg-warning/10 ring-1 ring-warning/40 animate-pulse"
              : chatOpen
                ? "text-primary bg-primary/10"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
          aria-label={chatOpen ? "Hide chat" : "Show chat"}
          title={
            gateNeedsAttention
              ? "Action needed — approve the safety gate (⌘\\)"
              : chatOpen
                ? "Hide chat (⌘\\)"
                : "Show chat (⌘\\)"
          }
        >
          <MessageSquare className="h-4 w-4" />
          {!chatOpen && (chatUnread > 0 || gateNeedsAttention) && (
            <span
              className={cn(
                "absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full text-[9px] font-semibold flex items-center justify-center",
                gateNeedsAttention
                  ? "bg-warning text-warning-foreground"
                  : "bg-primary text-primary-foreground"
              )}
            >
              {gateNeedsAttention ? "!" : chatUnread > 9 ? "9+" : chatUnread}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
