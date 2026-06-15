import { useState } from "react";
import { MessageSquare, History, FileDown } from "lucide-react";
import { toast } from "sonner";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { useArtifactStore } from "@/stores/artifactStore";
import { getPipelineStatus } from "@/lib/pipelineStatus";
import { downloadFromApi } from "@/lib/download";
import { cn } from "@/lib/utils";

// Drawings only exist once the design stage has produced detail drawings.
const DRAWINGS_READY_STATUSES = new Set(["design_complete", "report_generated"]);

export function WorkspaceHeader() {
  const { chatOpen, chatUnread, toggleChat } = useUIStore();
  const { isDrawerExpanded, setDrawerExpanded } = useArtifactStore();
  const { activeProject } = useProjectStore();
  const status = activeProject ? getPipelineStatus(activeProject.pipeline_status) : null;
  const [exportingDxf, setExportingDxf] = useState(false);

  const drawingsReady =
    !!activeProject && DRAWINGS_READY_STATUSES.has(activeProject.pipeline_status);

  const handleExportProjectDxf = async () => {
    if (!activeProject) return;
    setExportingDxf(true);
    try {
      await downloadFromApi(
        `/api/v1/drawings/${activeProject.project_id}/export/dxf`,
        `${activeProject.reference || activeProject.project_id}.dxf`
      );
    } catch {
      toast.error("No drawings are available to export yet.");
    } finally {
      setExportingDxf(false);
    }
  };

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-card shrink-0">
      {/* Left: project breadcrumb */}
      {activeProject && (
        <div className="text-xs text-foreground/70 font-medium">
          <span className="text-foreground">{activeProject.name}</span>
          <span className="mx-2 text-foreground/40">·</span>
          <span>{activeProject.reference}</span>
          <span className="mx-2 text-foreground/40">·</span>
          <span className={status?.textClass}>{status?.label}</span>
        </div>
      )}

      {/* Right: toggle buttons */}
      <div className="flex items-center gap-1">
        {/* Project-level DXF export — shown once detail drawings exist */}
        {drawingsReady && (
          <button
            onClick={handleExportProjectDxf}
            disabled={exportingDxf}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            aria-label="Export project drawings as DXF"
            title="Export all drawings as DXF"
          >
            <FileDown className="h-4 w-4" />
            {exportingDxf ? "Exporting…" : "DXF"}
          </button>
        )}

        {/* Artifacts toggle */}
        <button
          onClick={() => setDrawerExpanded(!isDrawerExpanded)}
          className={cn(
            "relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors",
            isDrawerExpanded
              ? "text-primary bg-primary/10"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
          aria-label={isDrawerExpanded ? "Hide artifacts" : "Show artifacts"}
          title={isDrawerExpanded ? "Hide artifacts" : "Show artifacts"}
        >
          <History className="h-4 w-4" />
        </button>

        {/* Chat toggle */}
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
      </div>
    </header>
  );
}
