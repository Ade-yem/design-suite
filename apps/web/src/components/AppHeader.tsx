import { StageTracker, type Stage } from "./StageTracker";
import { Hexagon, FolderOpen } from "lucide-react";
import { useRouter } from "next/navigation";
import { useProjectStore } from "@/stores/projectStore";

interface AppHeaderProps {
  currentStage: Stage;
}

export function AppHeader({ currentStage }: AppHeaderProps) {
  const router = useRouter();
  const { activeProject, clearActiveProject } = useProjectStore();

  const handleSwitchProject = () => {
    clearActiveProject();
    router.push("/dashboard");
  };

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-card">
      <div className="flex items-center gap-2.5">
        <Hexagon className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold tracking-tight">StructAI</span>
        <span className="text-xs text-muted-foreground font-mono">Copilot</span>
      </div>

      <StageTracker currentStage={currentStage} />

      <div className="flex items-center gap-3">
        <button
          onClick={handleSwitchProject}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors font-mono"
        >
          <FolderOpen className="h-3.5 w-3.5" />
          {activeProject ? activeProject.name : "No project"}
        </button>
      </div>
    </header>
  );
}
