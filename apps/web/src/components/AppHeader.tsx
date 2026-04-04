import { StageTracker, type Stage } from "./StageTracker";
import { Hexagon } from "lucide-react";

interface AppHeaderProps {
  currentStage: Stage;
}

export function AppHeader({ currentStage }: AppHeaderProps) {
  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-card">
      <div className="flex items-center gap-2.5">
        <Hexagon className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold tracking-tight">StructAI</span>
        <span className="text-xs text-muted-foreground font-mono">Copilot</span>
      </div>

      <StageTracker currentStage={currentStage} />

      <div className="flex items-center gap-3">
        <button className="text-xs text-muted-foreground hover:text-foreground transition-colors font-mono">
          Project: Untitled
        </button>
      </div>
    </header>
  );
}
