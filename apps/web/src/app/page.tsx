"use client";

import { JSX, useEffect, useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { ChatSidebar } from "@/components/ChatSidebar";
import {
  CanvasViewport,
  type CanvasViewportHandle,
} from "@/components/canvas/CanvasViewport";
import { ProjectSidebar } from "@/components/ProjectSidebar";
import { ProjectPrompt } from "@/components/ProjectPrompt";
import { NewProjectModal } from "@/components/NewProjectModal";
import { PipelineRail } from "@/components/PipelineRail";
import { ArtifactsDrawer } from "@/components/ArtifactsDrawer";
import { MemberAnalysisDrawer } from "@/components/analysis/MemberAnalysisDrawer";
import { pipelineStatusToStage } from "@/lib/pipelineStatus";
import { useProjectStore } from "@/stores/projectStore";
import { useUIStore } from "@/stores/uiStore";
import { useArtifactStore } from "@/stores/artifactStore";
import { useAnalysisStore } from "@/stores/analysisStore";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/project";
import { ProjectSocketProvider } from "@/hooks/useProjectSocket";

/**
 * UploadNudge component props.
 */
interface UploadNudgeProps {
  projectName: string;
  onBrowse: () => void;
  onDismiss: () => void;
}

/**
 * Renders a helpful onboarding nudge at the top of the workspace
 * to guide users to upload their DXF/PDF drawing when a new project is created.
 *
 * @param {UploadNudgeProps} props - Component properties.
 * @returns {JSX.Element} The rendered UploadNudge element.
 */
function UploadNudge({
  projectName,
  onBrowse,
  onDismiss,
}: UploadNudgeProps): JSX.Element {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-primary/10 border-b border-primary/20 animate-fade-in-up shrink-0">
      <Upload className="h-3.5 w-3.5 text-primary shrink-0" />
      <p className="flex-1 text-xs text-foreground">
        <span className="font-medium">{projectName}</span> created.{" "}
        <span className="text-muted-foreground">
          Upload a DXF or PDF drawing to begin structural analysis.
        </span>
      </p>
      <button
        onClick={onBrowse}
        className="shrink-0 px-3 py-1 bg-primary text-primary-foreground text-xs font-medium rounded-md hover:bg-primary/90 transition-colors"
      >
        Upload Drawing
      </button>
      <button
        onClick={onDismiss}
        className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/**
 * WorkspacePage root client component.
 * Sets up the multi-agent integrated development environment, isolating
 * custom toolbars, high-fidelity canvas contexts, and side-by-side conversational interfaces.
 *
 * @returns {JSX.Element} The rendered WorkspacePage element.
 */
export default function WorkspacePage(): JSX.Element {
  const {
    activeProject,
    refreshActiveProject,
    updateActiveProjectStatus,
    setActiveProject,
  } = useProjectStore();
  const { chatOpen, setChatOpen } = useUIStore();
  const { fetchArtifacts } = useArtifactStore();
  const clearAnalysis = useAnalysisStore((s) => s.clear);

  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [showUploadNudge, setShowUploadNudge] = useState(false);

  const canvasRef = useRef<CanvasViewportHandle>(null);

  const [chatWidth, setChatWidth] = useState(320);
  const [isResizing, setIsResizing] = useState(false);

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 280 && newWidth <= 700) {
        setChatWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      setIsResizing(false);
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  useKeyboardShortcuts({
    onNewProject: () => setShowNewProjectModal(true),
  });

  useEffect(() => {
    // Reset the per-member analysis drawer state whenever the project changes
    // so a drawer opened on a previous project never leaks across.
    clearAnalysis();
    if (activeProject) {
      refreshActiveProject().finally(() => {
      });
      fetchArtifacts(activeProject.project_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.project_id]);

  const currentStage = activeProject
    ? pipelineStatusToStage(activeProject.pipeline_status)
    : "parsing";

  const handleGateReached = (gate: string) => {
    const gateStatusMap: Record<string, { status: string; ordinal: number }> = {
      geometry_gate: { status: "geometry_verified", ordinal: 2 },
      loading_gate: { status: "loading_defined", ordinal: 3 },
      design_gate: { status: "design_complete", ordinal: 5 },
      drawing_gate: { status: "report_generated", ordinal: 6 },
    };
    const next = gateStatusMap[gate];
    if (next) updateActiveProjectStatus(next.status, next.ordinal);
  };

  const handleCreated = (project: Project) => {
    setActiveProject(project);
    setShowNewProjectModal(false);
    setShowUploadNudge(true);
  };

  return (
    <div className="h-screen flex overflow-hidden">
      <ProjectSidebar />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {activeProject ? (
          <ProjectSocketProvider projectId={activeProject.project_id}>
            <WorkspaceHeader />

            {/* Upload nudge — shown immediately after project creation */}
            {showUploadNudge && (
              <UploadNudge
                projectName={activeProject.name}
                onBrowse={() => {
                  canvasRef.current?.triggerFilePicker();
                  setShowUploadNudge(false);
                }}
                onDismiss={() => setShowUploadNudge(false)}
              />
            )}

            <div className="flex-1 flex min-h-0 overflow-hidden">
              <PipelineRail
                projectId={activeProject.project_id}
                currentStage={currentStage}
                pipelineStatus={activeProject.pipeline_status}
              />
              <div className="flex-1 min-w-0 overflow-hidden">
                <CanvasViewport
                  ref={canvasRef}
                  projectId={activeProject.project_id}
                  onParsed={() => refreshActiveProject()}
                  onUploadStart={() => setShowUploadNudge(false)}
                />
              </div>
              {/* Right side: Member analysis drawer + Artifacts drawer + Chat sidebar */}
              <div className="flex shrink-0 overflow-hidden relative">
                <MemberAnalysisDrawer />
                <ArtifactsDrawer />
                {chatOpen && (
                  <div
                    onMouseDown={startResize}
                    className={cn(
                      "w-1 h-full cursor-ew-resize hover:bg-primary/50 active:bg-primary transition-colors z-50",
                      isResizing ? "bg-primary" : "bg-transparent border-l border-border/40"
                    )}
                  />
                )}
                <div
                  className={cn(
                    "shrink-0 overflow-hidden h-full",
                    !isResizing && "transition-[width] duration-200 ease-out"
                  )}
                  style={{ width: chatOpen ? `${chatWidth}px` : "0px" }}
                >
                  <div className="h-full" style={{ width: `${chatWidth}px` }}>
                    <ChatSidebar
                      projectId={activeProject.project_id}
                      onGateReached={handleGateReached}
                      onClose={() => setChatOpen(false)}
                    />
                  </div>
                </div>
              </div>
            </div>
          </ProjectSocketProvider>
        ) : (
          <ProjectPrompt />
        )}
      </div>

      {showNewProjectModal && (
        <NewProjectModal
          onClose={() => setShowNewProjectModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
